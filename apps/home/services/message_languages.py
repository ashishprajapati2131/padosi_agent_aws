"""Pre-drafted messages in English plus India's 22 scheduled languages.

Editors keep the message's base text where it always lived and store the other
languages next to it as {code: text}. Readers call pick(); nothing translates at
request time. translate_texts() fills languages through the existing LLM chain
(Groq -> Gemini -> OpenRouter) when an admin or agent presses "Translate".
"""

import hashlib
import json
import logging
import re
from collections import Counter

from django.core.cache import cache

logger = logging.getLogger(__name__)

# (code, English name, native name). English first, then the languages most of
# our agents use, then the rest of the Eighth Schedule alphabetically.
LANGUAGES = [
    ("en", "English", "English"),
    ("gu", "Gujarati", "ગુજરાતી"),
    ("hi", "Hindi", "हिन्दी"),
    ("mr", "Marathi", "मराठी"),
    ("as", "Assamese", "অসমীয়া"),
    ("bn", "Bengali", "বাংলা"),
    ("brx", "Bodo", "बड़ो"),
    ("doi", "Dogri", "डोगरी"),
    ("kn", "Kannada", "ಕನ್ನಡ"),
    ("ks", "Kashmiri", "کٲشُر"),
    ("kok", "Konkani", "कोंकणी"),
    ("mai", "Maithili", "मैथिली"),
    ("ml", "Malayalam", "മലയാളം"),
    ("mni", "Manipuri", "মৈতৈলোন্"),
    ("ne", "Nepali", "नेपाली"),
    ("or", "Odia", "ଓଡ଼ିଆ"),
    ("pa", "Punjabi", "ਪੰਜਾਬੀ"),
    ("sa", "Sanskrit", "संस्कृतम्"),
    ("sat", "Santali", "ᱥᱟᱱᱛᱟᱲᱤ"),
    ("sd", "Sindhi", "سنڌي"),
    ("ta", "Tamil", "தமிழ்"),
    ("te", "Telugu", "తెలుగు"),
    ("ur", "Urdu", "اردو"),
]
LANGUAGE_CODES = {code for code, _, _ in LANGUAGES}
LANGUAGE_NAMES = {code: name for code, name, _ in LANGUAGES}

MAX_TEXT_LENGTH = 2000
MAX_LANGS_PER_CALL = 8
_CACHE_TTL = 60 * 60 * 24 * 30

# Tokens a translation must keep exactly: {name}, {{agent_name}}, URLs.
_PROTECTED_RE = re.compile(r"\{\{\s*\w+\s*\}\}|\{\w+\}|https?://[^\s\"'<>]+")


def normalize_lang(code):
    code = str(code or "").strip().lower()
    return code if code in LANGUAGE_CODES else "en"


def request_language(request):
    """The language the visitor picked in the site's language widget, else English."""
    lang = request.COOKIES.get("padosi_lang", "")
    if not lang:
        # Google Translate's own cookie looks like "/en/gu".
        lang = request.COOKIES.get("googtrans", "").rstrip("/").rsplit("/", 1)[-1]
    return normalize_lang(lang)


def clean_translations(value, max_length=MAX_TEXT_LENGTH):
    """Keep only known language codes with non-empty text; accepts a dict or JSON text."""
    if isinstance(value, str):
        try:
            value = json.loads(value) if value.strip() else {}
        except ValueError:
            return {}
    if not isinstance(value, dict):
        return {}
    cleaned = {}
    for code, text in value.items():
        if code in LANGUAGE_CODES and isinstance(text, str) and text.strip():
            cleaned[code] = text.strip()[:max_length]
    return cleaned


def pick(base_text, translations, lang):
    """The text for `lang`, falling back to the base text."""
    if lang and isinstance(translations, dict):
        text = translations.get(lang)
        if isinstance(text, str) and text.strip():
            return text
    return base_text


def protected_tokens(text):
    return Counter(_PROTECTED_RE.findall(text or ""))


def _cache_key(text, lang):
    return "msg_tr:%s:%s" % (
        lang,
        hashlib.sha256(text.encode("utf-8")).hexdigest()[:40],
    )


def _extract_json(content):
    match = re.search(r"\{.*\}", content or "", re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _ask_llm(text, langs):
    from apps.chatbot.llm_client import call_llm_with_fallback

    targets = ", ".join("%s (%s)" % (code, LANGUAGE_NAMES[code]) for code in langs)
    messages = [
        {
            "role": "system",
            "content": (
                "You translate short WhatsApp/SMS messages written by Indian insurance agents. "
                "Translate the user's message into each requested language, in that language's usual script. "
                "Keep the tone warm and natural, keep line breaks and emojis. "
                "Copy these exactly, untranslated: anything in {braces} or {{double braces}}, URLs, "
                "and the brand name PadosiAgent. "
                'Reply with only a JSON object mapping each language code to its translation, e.g. {"hi": "..."}.'
            ),
        },
        {"role": "user", "content": "Languages: %s\n\nMessage:\n%s" % (targets, text)},
    ]
    response, _provider = call_llm_with_fallback(
        messages, total_deadline=40.0, timeout=30.0, temperature=0.2, max_tokens=4000
    )
    return _extract_json(response.choices[0].message.content)


def translate_texts(text, langs):
    """Translate `text` into `langs`; returns {code: text} for the ones that worked.

    Results are cached per (text, language). A translation that drops or changes a
    placeholder or link is thrown away rather than sent to clients broken.
    """
    text = (text or "").strip()
    langs = [code for code in dict.fromkeys(langs) if code in LANGUAGE_CODES]
    if not text or not langs:
        return {}

    result = {}
    missing = []
    for code in langs:
        cached = cache.get(_cache_key(text, code))
        if cached:
            result[code] = cached
        else:
            missing.append(code)
    if not missing:
        return result

    try:
        raw = _ask_llm(text, missing)
    except Exception:
        logger.warning(
            "Message translation failed for %s", ",".join(missing), exc_info=True
        )
        return result

    wanted = protected_tokens(text)
    for code in missing:
        translated = raw.get(code)
        if not isinstance(translated, str) or not translated.strip():
            continue
        translated = translated.strip()[:MAX_TEXT_LENGTH]
        if protected_tokens(translated) != wanted:
            logger.info("Dropped %s translation: placeholders or links changed", code)
            continue
        cache.set(_cache_key(text, code), translated, _CACHE_TTL)
        result[code] = translated
    return result
