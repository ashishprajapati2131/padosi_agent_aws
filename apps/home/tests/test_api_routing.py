"""Every Django URL under /api/ must be routed to Django by asgi.py / passenger_wsgi.py.

The test client skips that routing, so a missing prefix 404s only in production (audit WEB2).
"""

from django.test import SimpleTestCase
from django.urls import URLPattern, URLResolver, get_resolver
from django.urls.resolvers import RoutePattern

from padosi_agent.api_routing import is_fastapi_path

# Django twins of routes FastAPI serves itself (FastAPI answers first by design).
SERVED_BY_FASTAPI = {"/api/v1/csrf-refresh/"}


def _django_api_paths(patterns=None, prefix=""):
    patterns = get_resolver().url_patterns if patterns is None else patterns
    for p in patterns:
        if not isinstance(p.pattern, RoutePattern):
            continue
        route = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            yield from _django_api_paths(p.url_patterns, route)
        elif isinstance(p, URLPattern) and route.startswith("api/"):
            yield "/" + route.split("<", 1)[0]


class DjangoApiRoutingTests(SimpleTestCase):
    def test_every_django_api_url_stays_in_django(self):
        paths = set(_django_api_paths()) - SERVED_BY_FASTAPI
        self.assertIn("/api/quick-lead-capture/", paths)
        leaked = sorted(p for p in paths if is_fastapi_path(p))
        self.assertEqual(leaked, [], "Add these prefixes to DJANGO_API_PREFIXES")

    def test_fastapi_paths_still_go_to_fastapi(self):
        for path in ("/api/auth/login", "/api/leads/", "/api/v1/csrf-refresh/"):
            self.assertTrue(is_fastapi_path(path), path)
