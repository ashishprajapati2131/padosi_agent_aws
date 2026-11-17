from django.conf import settings

from apps.localization import services


# Header logo per language (static/img/logos/padosi-<code>.webp, 141px tall) -> display width at 47px.
LANGUAGE_LOGO_WIDTHS = {
    "en": 156,
    "hi": 160,
    "gu": 161,
    "mr": 167,
    "ta": 170,
    "kn": 165,
    "ml": 167,
    "bn": 166,
    "pa": 168,
    "te": 172,
    "or": 170,
    "as": 151,
}


def localization(request):
    """Current language, switcher options and hreflang alternates for templates."""
    config = services.get_config()
    services.sync_ui_overrides(
        config["ui_version"]
    )  # portal pages skip the middleware load
    language = getattr(request, "LANGUAGE_CODE", settings.LANGUAGE_CODE)
    context = {
        "current_language": language,
        "language_prefix": getattr(request, "language_prefix", ""),
        "site_languages": config["languages"] if len(config["codes"]) > 1 else (),
    }
    logo_code = language if language in LANGUAGE_LOGO_WIDTHS else settings.LANGUAGE_CODE
    context["language_logo"] = f"img/logos/padosi-{logo_code}.webp"
    context["language_logo_width"] = LANGUAGE_LOGO_WIDTHS[logo_code]
    if context["site_languages"] and services.is_localizable(request.path):
        from apps.agents.services.og_urls import build_og_absolute_url

        context["hreflang_alternates"] = [
            (
                code,
                build_og_absolute_url(
                    request, services.localize_path(request.path, code)
                ),
            )
            for code, _name in config["languages"]
        ]
        context["hreflang_x_default"] = build_og_absolute_url(request, request.path)
    return context
