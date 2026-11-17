from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils import translation
from django.utils.cache import patch_vary_headers
from django.utils.encoding import escape_uri_path

from apps.localization import services


def _redirect(request, path):
    query = request.META.get("QUERY_STRING", "")
    response = HttpResponseRedirect(
        escape_uri_path(path) + ("?" + query if query else "")
    )
    patch_vary_headers(response, ("Cookie", "Accept-Language"))
    return response


def _rewrite_path(request, path):
    script_name = request.path[: len(request.path) - len(request.path_info)]
    request.path_info = path
    request.path = script_name + path
    request.META["PATH_INFO"] = path


class LanguageMiddleware:
    """Takes the place of Django's LocaleMiddleware for the /<code>/ URL scheme.

    A language prefix is stripped from request.path / path_info before routing, so
    every later middleware (payment gate, WAF, admin RBAC, SEO headers) and every
    URLconf sees exactly the paths it saw before localization existed.

    Unprefixed public pages redirect (302) to the visitor's preferred language,
    except for bots, AJAX and non-GET requests. Prefixed URLs never redirect to
    another language, so there are no loops and crawlers can reach every version.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        code, rest = services.split_language_prefix(request.path_info)
        cookies = {}
        language, prefix, varies = services.SOURCE_LANGUAGE, "", False
        # Portal, payment, registration and API requests never touch localization config:
        # no extra queries or cache reads on those hot paths.
        config = None
        if code or services.is_localizable(request.path_info):
            config = services.get_config()
            services.sync_ui_overrides(config["ui_version"])

        if code:
            _rewrite_path(request, rest)
            usable = (
                code in config["codes"]
                and code != services.SOURCE_LANGUAGE
                and services.is_localizable(rest)
            )
            if usable:
                language, prefix = code, "/" + code
            elif request.method in ("GET", "HEAD"):
                # /en/..., disabled languages and portal paths live at the unprefixed URL.
                return _redirect(request, rest)
        elif config and len(config["codes"]) > 1:
            varies = True
            preferred, cookies = services.resolve_preferred_language(request, config)
            if (
                preferred != services.SOURCE_LANGUAGE
                and request.method in ("GET", "HEAD")
                and request.headers.get("x-requested-with") != "XMLHttpRequest"
                and not services.is_bot(request)
            ):
                response = _redirect(
                    request, services.localize_path(request.path_info, preferred)
                )
                services.apply_cookies(response, cookies)
                return response

        translation.activate(language)
        request.LANGUAGE_CODE = language
        request.language_prefix = prefix
        response = self.get_response(request)
        response.headers.setdefault("Content-Language", language)
        if varies:
            patch_vary_headers(response, ("Cookie", "Accept-Language"))
        services.apply_cookies(response, cookies)
        return response
