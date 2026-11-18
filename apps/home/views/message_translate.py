import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.home.services.message_languages import (
    LANGUAGE_CODES,
    MAX_LANGS_PER_CALL,
    MAX_TEXT_LENGTH,
    translate_texts,
)
from apps.home.views.leads import _rate_limited


def _caller_key(request):
    """Who is asking: a logged-in agent/distributor/insurance user or an admin session."""
    if request.user.is_authenticated:
        return "u%s" % request.user.pk
    from apps.admin_panel.auth import _get_admin_from_session

    admin_id = _get_admin_from_session(request)
    return "a%s" % admin_id if admin_id else None


@require_POST
def translate_message(request):
    """Translate one pre-drafted message into up to MAX_LANGS_PER_CALL languages."""
    caller = _caller_key(request)
    if not caller:
        return JsonResponse({"ok": False, "error": "Please log in again."}, status=403)

    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)

    text = str(data.get("text") or "").strip()
    langs = data.get("langs")
    if not text or len(text) > MAX_TEXT_LENGTH:
        return JsonResponse(
            {
                "ok": False,
                "error": "Message must be 1-%d characters." % MAX_TEXT_LENGTH,
            },
            status=400,
        )
    if (
        not isinstance(langs, list)
        or not 0 < len(langs) <= MAX_LANGS_PER_CALL
        or any(code not in LANGUAGE_CODES for code in langs)
    ):
        return JsonResponse({"ok": False, "error": "Unknown language."}, status=400)

    # Each call is one LLM request; 22 languages are 3 calls, so this allows ~20 full translations an hour.
    if _rate_limited("msg_translate:%s" % caller, 60, 3600):
        return JsonResponse(
            {
                "ok": False,
                "error": "Too many translations. Please try again in an hour.",
            },
            status=429,
        )

    translations = translate_texts(text, langs)
    return JsonResponse(
        {
            "ok": True,
            "translations": translations,
            "missing": [code for code in langs if code not in translations],
        }
    )
