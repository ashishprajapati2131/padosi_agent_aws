from urllib.parse import urlsplit

from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.localization import services
from apps.localization.models import UserLanguagePreference


@require_POST
def set_language(request):
    """Language switcher target: remembers the explicit choice and returns to the same page
    (path + query) in the chosen language."""
    next_url = request.POST.get("next") or "/"
    if not next_url.startswith("/") or not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = "/"
    parts = urlsplit(next_url)
    _old, path = services.split_language_prefix(parts.path or "/")
    path = "/" + path.lstrip("/\\")

    language = request.POST.get("language", "")
    if language not in services.get_config()["codes"]:
        return HttpResponseRedirect(next_url)

    target = services.localize_path(path, language) + (
        "?" + parts.query if parts.query else ""
    )
    response = HttpResponseRedirect(target)
    services.set_language_cookie(response, language)
    if request.user.is_authenticated:
        UserLanguagePreference.objects.update_or_create(
            user=request.user, defaults={"language": language}
        )
    return response
