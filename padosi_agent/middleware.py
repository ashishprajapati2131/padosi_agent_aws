from django.utils.deprecation import MiddlewareMixin
import re

class SEOMiddleware(MiddlewareMixin):
    """
    Adds X-Robots-Tag to HTTP headers for private paths to prevent indexing.
    """
    def __init__(self, get_response):
        super().__init__(get_response)
        self.private_paths = [
            r'^/django-admin/',
            r'^/agent-login/',
            r'^/agent/dashboard/',
            r'^/insurance-login/',
            r'^/media/app/private/',
            r'^/api/',
        ]
        self.compiled_paths = [re.compile(path) for path in self.private_paths]

    def process_response(self, request, response):
        path = request.path
        if any(regex.match(path) for regex in self.compiled_paths):
            response['X-Robots-Tag'] = 'noindex, nofollow'
        return response
