import logging
from django.utils.deprecation import MiddlewareMixin
from django.middleware.csrf import get_token
import re

logger = logging.getLogger(__name__)


class StaleCookieSanitizerMiddleware:
    """
    Sanitizes malformed or corrupted HTTP_COOKIE header strings before Django parses them.
    Prevents 400 Bad Request or Cookie parsing crashes for end clients.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raw_cookie = request.META.get('HTTP_COOKIE', '')
        if raw_cookie:
            sanitized = re.sub(r'[\x00-\x1F\x7F]', '', raw_cookie)
            if sanitized != raw_cookie:
                request.META['HTTP_COOKIE'] = sanitized
        return self.get_response(request)


class AutoCsrfCookieMiddleware:
    """
    Ensures every GET HTML response guarantees a valid CSRF cookie on the client's browser,
    so client forms never render with a blank or missing CSRF token.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.method == 'GET' and response.status_code == 200:
            token = get_token(request)
            if token and 'padosi_csrf_token' not in request.COOKIES:
                response.set_cookie('padosi_csrf_token', token, path='/', samesite='Lax')
        return response


class SEOMiddleware(MiddlewareMixin):
    """
    Adds X-Robots-Tag to HTTP headers for private paths to prevent indexing.
    """
    def __init__(self, get_response):
        super().__init__(get_response)
        self.private_paths = [
            r'^/admin/',
            r'^/django-admin/',
            r'^/agent-login/',
            r'^/agent/dashboard/',
            r'^/insurance-login/',
            r'^/media/app/private/',
            r'^/api/',
        ]
        self.compiled_paths = [re.compile(path) for path in self.private_paths]

    # Deliberately minimal CSP: blocks <base> hijacking and plugin content
    # (<object>/<embed>, none used by the site) without restricting scripts,
    # styles, fonts or CDNs, so no existing page can break.
    BASE_CSP = "base-uri 'self'; object-src 'none'"

    def process_response(self, request, response):
        path = request.path
        if any(regex.match(path) for regex in self.compiled_paths):
            response['X-Robots-Tag'] = 'noindex, nofollow'
        content_type = response.get('Content-Type', '') or ''
        if 'text/html' in content_type and 'Content-Security-Policy' not in response:
            response['Content-Security-Policy'] = self.BASE_CSP
        return response
