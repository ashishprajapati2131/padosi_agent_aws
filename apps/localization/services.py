"""Language resolution for the public site.

URL scheme: unprefixed URLs serve the source language (settings.LANGUAGE_CODE);
/<code>/<path> serves <path> in <code>. Only public pages are localizable; portals,
payment, APIs and technical paths always stay unprefixed.
"""

import hashlib
import hmac
import ipaddress
import logging
import re
import threading

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError
from django.utils.translation.trans_real import parse_accept_lang_header

logger = logging.getLogger(__name__)

KNOWN_CODES = frozenset(code for code, _ in settings.LANGUAGES)
SOURCE_LANGUAGE = settings.LANGUAGE_CODE

CONFIG_CACHE_KEY = "localization:config:v1"
CONFIG_TTL = 300
GEO_CACHE_TTL = 24 * 60 * 60
GEO_COOKIE = "padosi_geo_lang"
GEO_COOKIE_SALT = "padosi-geo-lang"
GEO_COOKIE_AGE = 24 * 60 * 60

# First path segment that is never localized (portals, payment, auth, APIs, technical files).
NON_LOCALIZABLE_SEGMENTS = frozenset(
    {
        "static",
        "media",
        "admin",
        "django-admin",
        "api",
        "ajax",
        "chatbot-api",
        "wa-bot",
        "i18n",
        "healthz",
        "sitemap.xml",
        "robots.txt",
        "favicon.ico",
        "manifest.webmanifest",
        "sw.js",
        "offline.html",
        "insurance",
        "insurance-login",
        "distributor",
        "distributor-login",
        "distributor-logout",
        "sub-distributor",
        "wholesale",
        "wholesaler",
        "agent",
        "agent-login",
        "agent-logout",
        "agent-check-email",
        "agent-check-slug",
        "chooseplan",
        "payments",
        "razorpay-webhook",
        "webhook",
        "logout",
        "auth",
        "client",
        "client-login",
        "join",
        "invite",
        "participants",
        "events",
        "48HR",
        "48hr",
        "event-registration",
        "stall-leaderboard",
        "og-image",
        "qr",
        "review",
        "review-card",
        "verify-promo",
        "quick-registration",
        "forgot-password",
        "reset-password",
        "test-mode",
        "simulator",
        "welcome-preview",
        "notify",
        "message",
        "settings",
        "subusers",
        "dashboard",
        "coming-soon",
        "card",
    }
)
NON_LOCALIZABLE_PREFIXES = ("agent-register", "payment", "health", "plan-")

_BOT_RE = re.compile(
    r"bot|crawl|spider|slurp|facebookexternalhit|whatsapp|telegram|lighthouse|headless|preview|"
    r"curl|wget|python-requests|httpclient|monitor",
    re.I,
)
_PROFILE_PATH_RE = re.compile(r"^/([A-Za-z0-9_-]{1,200})/(?:review/)?$")


# ── Paths ────────────────────────────────────────────────────────────────────


def is_localizable(path):
    segment = path[1:].split("/", 1)[0]
    return segment not in NON_LOCALIZABLE_SEGMENTS and not segment.startswith(
        NON_LOCALIZABLE_PREFIXES
    )


def _state_codes():
    from apps.agents.models import STATE_CODE_MAP

    return set(STATE_CODE_MAP.values())


def is_agent_profile_path(code, rest):
    """/as/<slug>/ (Assam) and /ml/<slug>/ (Meghalaya) are existing agent profile URLs
    that look like language prefixes. An existing agent wins over the language."""
    if code not in _state_codes():
        return False
    match = _PROFILE_PATH_RE.match(rest)
    if not match:
        return False
    slug = match.group(1)
    key = "localization:profile-slug:" + hashlib.sha256(slug.encode()).hexdigest()
    hit = cache.get(key)
    if hit is None:
        from apps.agents.models import Agent

        try:
            hit = Agent.objects.filter(profile__slug=slug).exists() or (
                slug.isdigit() and Agent.objects.filter(id=int(slug)).exists()
            )
        except DatabaseError:
            logger.warning("Agent profile prefix check failed", exc_info=True)
            return False
        cache.set(key, hit, 600)
    return hit


def split_language_prefix(path):
    """'/gu/about/' -> ('gu', '/about/'). Returns (None, path) when there is no language prefix."""
    segment, _, rest = path[1:].partition("/")
    if segment not in KNOWN_CODES:
        return None, path
    # Leading slashes/backslashes would turn the remainder into a protocol-relative URL.
    rest = "/" + rest.lstrip("/\\")
    if is_agent_profile_path(segment, rest):
        return None, path
    return segment, rest


def localize_path(path, code):
    if code == SOURCE_LANGUAGE or code not in KNOWN_CODES or not is_localizable(path):
        return path
    return f"/{code}{path}"


# ── Admin-managed configuration (cached) ─────────────────────────────────────

_FALLBACK_CONFIG = {
    "languages": ((SOURCE_LANGUAGE, "English"),),
    "codes": frozenset({SOURCE_LANGUAGE}),
    "states": {},
    "auto_detect": False,
    "browser": False,
    "default": SOURCE_LANGUAGE,
    "enabled": False,
    "ui_version": None,
}


def get_config():
    config = cache.get(CONFIG_CACHE_KEY)
    if config is not None:
        return config
    from apps.localization.models import (
        LocalizationSettings,
        SiteLanguage,
        StateLanguage,
        UITranslation,
    )
    from django.db.models import Count, Max

    try:
        languages = tuple(
            (lang.code, lang.native_name)
            for lang in SiteLanguage.objects.filter(
                is_active=True, code__in=KNOWN_CODES
            )
        )
        codes = frozenset(code for code, _ in languages) | {SOURCE_LANGUAGE}
        states = {}
        for state in StateLanguage.objects.all():
            language = state.language_id if state.language_id in codes else None
            for key in (state.state_code, state.state_name, *state.aliases.split(",")):
                if key.strip():
                    states[key.strip().upper()] = language
        site = LocalizationSettings.objects.filter(pk=1).first()
        ui = UITranslation.objects.aggregate(n=Count("id"), last=Max("updated_at"))
    except DatabaseError:
        # Tables not migrated yet: serve the source language only, and don't cache that.
        logger.warning(
            "Localization config unavailable; serving %s only",
            SOURCE_LANGUAGE,
            exc_info=True,
        )
        return _FALLBACK_CONFIG
    if site and not site.enabled:  # master switch OFF: English only, nothing detected
        languages, codes, states = (), frozenset({SOURCE_LANGUAGE}), {}
    default = (
        site.default_language_id
        if site and site.default_language_id in codes
        else SOURCE_LANGUAGE
    )
    config = {
        "languages": languages or _FALLBACK_CONFIG["languages"],
        "codes": codes,
        "states": states,
        "auto_detect": site.auto_detect_enabled if site else True,
        "browser": site.browser_language_enabled if site else True,
        "default": default,
        "enabled": site.enabled if site else True,
        # Changes whenever an admin edits website text; each process re-applies overrides then.
        "ui_version": f"{ui['n']}:{ui['last']}",
    }
    cache.set(CONFIG_CACHE_KEY, config, CONFIG_TTL)
    return config


def clear_config_cache():
    cache.delete(CONFIG_CACHE_KEY)


# ── Website text edited in the admin panel (overrides locale/*.po) ──────────

_applied_ui_version = None
_ui_lock = threading.Lock()


def sync_ui_overrides(version):
    """Reload gettext catalogs and layer admin edits on top, once per change per process."""
    global _applied_ui_version
    if version is None or version == _applied_ui_version:
        return
    with _ui_lock:
        if version == _applied_ui_version:
            return
        import gettext

        from django.utils.translation import trans_real

        from apps.localization.models import UITranslation

        # Same reset Django does when a .mo file changes in development.
        gettext._translations = {}
        trans_real._translations = {}
        trans_real._default = None
        try:
            rows = list(UITranslation.objects.values_list("language", "msgid", "text"))
        except DatabaseError:
            return
        for language, msgid, text in rows:
            if text and language in KNOWN_CODES:
                trans_real.translation(language)._catalog[msgid] = text
        _applied_ui_version = version


def website_messages():
    """Every translatable website text (msgid) found in locale/*/django.po, in file order."""
    from apps.localization.po import parse_po, po_path

    seen = {}
    for code in KNOWN_CODES:
        path = po_path(code)
        if path.exists():
            for msgid, _text, _fuzzy in parse_po(path.read_text(encoding="utf-8")):
                if msgid:
                    seen.setdefault(msgid, None)
    return list(seen)


def po_translations(language):
    """{msgid: text} from the language's .po file (the shipped default wording)."""
    from apps.localization.po import parse_po, po_path

    if language == SOURCE_LANGUAGE:
        return {}
    path = po_path(language)
    if not path.exists():
        return {}
    return {m: t for m, t, fuzzy in parse_po(path.read_text(encoding="utf-8")) if m and t and not fuzzy}


def clean_ui_text(msgid, text):
    """Admin-entered text is rendered unescaped by {% translate %}: strip tags, or sanitize
    when the original text itself carries markup (e.g. the brand spans)."""
    from django.utils.html import strip_tags

    from apps.home.html_sanitizer import sanitize_html

    text = (text or "").strip()
    return sanitize_html(text) if "<" in msgid else strip_tags(text)


def translation_completion(language, messages=None, overrides=None):
    """(translated, total) counting both the .po file and admin edits."""
    messages = messages if messages is not None else website_messages()
    if language == SOURCE_LANGUAGE:
        return len(messages), len(messages)
    if overrides is None:
        from apps.localization.models import UITranslation

        overrides = set(UITranslation.objects.filter(language=language).exclude(text="").values_list("msgid", flat=True))
    shipped = po_translations(language)
    done = sum(1 for m in messages if m in shipped or m in overrides)
    return done, len(messages)


# ── GeoIP ────────────────────────────────────────────────────────────────────

_reader = None
_reader_failed = False
_reader_lock = threading.Lock()


def _geoip_reader():
    """MaxMind GeoLite2/GeoIP2 City reader, opened once per process. None when unavailable."""
    global _reader, _reader_failed
    if _reader is not None or _reader_failed:
        return _reader
    with _reader_lock:
        if _reader is None and not _reader_failed:
            path = getattr(settings, "GEOIP_CITY_DB", "")
            try:
                import geoip2.database

                _reader = geoip2.database.Reader(path)
            except (
                Exception
            ) as exc:  # missing package or database file: detection is just off
                _reader_failed = True
                logger.warning(
                    "GeoIP disabled (%s): set GEOIP_CITY_DB to a GeoLite2-City.mmdb file",
                    type(exc).__name__,
                )
    return _reader


def lookup_indian_state(ip):
    """(subdivision_code, subdivision_name) for an Indian IP, else None. Results are cached
    under a keyed hash so the raw IP never lands in the cache."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if not address.is_global:
        return None
    digest = hmac.new(
        settings.SECRET_KEY.encode(), str(address).encode(), hashlib.sha256
    ).hexdigest()
    key = "localization:geo:" + digest
    cached = cache.get(key)
    if cached is not None:
        return tuple(cached) or None
    result = ()
    reader = _geoip_reader()
    if reader is not None:
        try:
            response = reader.city(str(address))
            if response.country.iso_code == "IN":
                subdivision = response.subdivisions.most_specific
                result = (subdivision.iso_code or "", subdivision.name or "")
        except (
            Exception
        ):  # AddressNotFoundError and corrupt-record errors: treat as unknown
            result = ()
    cache.set(key, result, GEO_CACHE_TTL)
    return result or None


def language_for_state(state, config):
    if not state:
        return None
    code, name = state
    states = config["states"]
    return states.get(code.upper()) or states.get(name.upper())


def client_ip(request):
    from apps.admin_panel.middleware import ThreatMonitorMiddleware

    return ThreatMonitorMiddleware.get_client_ip(request)


# ── Preference resolution ────────────────────────────────────────────────────


def saved_user_language(request):
    from django.contrib.auth import SESSION_KEY

    from apps.localization.models import UserLanguagePreference

    user_id = request.session.get(SESSION_KEY) if hasattr(request, "session") else None
    if not user_id:
        return None
    try:
        return (
            UserLanguagePreference.objects.filter(user_id=user_id)
            .values_list("language", flat=True)
            .first()
        )
    except (DatabaseError, ValueError):
        return None


def browser_language(request, codes):
    header = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
    for tag, _quality in parse_accept_lang_header(header):
        code = tag.split("-")[0]
        if code in codes:
            return code
    return None


def resolve_preferred_language(request, config):
    """Priority: explicit/saved choice (cookie) > signed-in user's profile > GeoIP state >
    browser Accept-Language > admin default. Returns (language, cookies_to_set)."""
    codes = config["codes"]
    cookies = {}
    language = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
    if language in codes:
        return language, cookies
    language = saved_user_language(request)
    if language in codes:
        cookies[settings.LANGUAGE_COOKIE_NAME] = language
        return language, cookies
    if config["auto_detect"]:
        language = request.get_signed_cookie(
            GEO_COOKIE, default=None, salt=GEO_COOKIE_SALT
        )
        if language is None:
            language = (
                language_for_state(lookup_indian_state(client_ip(request)), config)
                or ""
            )
            cookies[GEO_COOKIE] = language
        if language in codes:
            return language, cookies
    if config["browser"]:
        language = browser_language(request, codes)
        if language:
            return language, cookies
    return config["default"], cookies


def is_bot(request):
    agent = request.META.get("HTTP_USER_AGENT", "")
    return not agent or bool(_BOT_RE.search(agent))


def set_language_cookie(response, language):
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        language,
        max_age=settings.LANGUAGE_COOKIE_AGE,
        path=settings.LANGUAGE_COOKIE_PATH,
        domain=settings.LANGUAGE_COOKIE_DOMAIN,
        secure=settings.LANGUAGE_COOKIE_SECURE,
        httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
        samesite=settings.LANGUAGE_COOKIE_SAMESITE,
    )


def apply_cookies(response, cookies):
    for name, value in cookies.items():
        if name == GEO_COOKIE:
            response.set_signed_cookie(
                GEO_COOKIE,
                value,
                salt=GEO_COOKIE_SALT,
                max_age=GEO_COOKIE_AGE,
                path="/",
                secure=settings.LANGUAGE_COOKIE_SECURE,
                httponly=True,
                samesite="Lax",
            )
        else:
            set_language_cookie(response, value)


# ── Database content translations ────────────────────────────────────────────


def content_translation_cache_key(content_type_id, object_id, field, language):
    return f"localization:ct:{content_type_id}:{object_id}:{field}:{language}"


def translated_field(obj, field, language):
    """Approved admin translation of obj.<field> in `language`, else the original value."""
    original = getattr(obj, field, "")
    if language == SOURCE_LANGUAGE or obj is None or getattr(obj, "pk", None) is None:
        return original
    from django.contrib.contenttypes.models import ContentType

    from apps.localization.models import ContentTranslation

    try:
        content_type = ContentType.objects.get_for_model(obj)
        key = content_translation_cache_key(content_type.pk, obj.pk, field, language)
        text = cache.get(key)
        if text is None:
            text = (
                ContentTranslation.objects.filter(
                    content_type=content_type,
                    object_id=str(obj.pk),
                    field=field,
                    language=language,
                    is_approved=True,
                )
                .values_list("text", flat=True)
                .first()
                or ""
            )
            cache.set(key, text, CONFIG_TTL)
    except DatabaseError:
        return original
    return text or original
