"""FastAPI rate limits must hold across Passenger processes: counters live in
the shared Django cache, not per-process memory."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "api-rl",
    }
}


@override_settings(CACHES=LOCMEM)
class SharedApiRateLimitTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def _process(self):
        """A separate app + middleware instance stands in for another process."""
        from fastapi import FastAPI
        from starlette.testclient import TestClient
        from fastapi_app.middleware.rate_limiter import RateLimitMiddleware

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, requests_limit=3, window_seconds=60)
        app.get("/ping")(lambda: {"ok": True})
        return TestClient(app)

    def test_middleware_counts_are_shared_between_processes(self):
        a, b = self._process(), self._process()
        with patch(
            "fastapi_app.utils.client_ip.get_client_ip", return_value="198.51.100.7"
        ):
            self.assertEqual(a.get("/ping").status_code, 200)
            self.assertEqual(a.get("/ping").status_code, 200)
            self.assertEqual(b.get("/ping").status_code, 200)
            res = b.get("/ping")
        self.assertEqual(res.status_code, 429)
        self.assertEqual(
            res.json(),
            {
                "error": "Too Many Requests",
                "message": "Rate limit exceeded. Please try again later.",
            },
        )

    def test_login_ip_throttle_uses_shared_cache(self):
        from fastapi_app.services import auth_service

        auth_service.login_attempts_store.clear()
        ip = "198.51.100.8"
        for _ in range(6):
            self.assertTrue(auth_service.check_login_throttle(ip))
            auth_service.record_login_attempt(ip)
        self.assertFalse(auth_service.check_login_throttle(ip))
        self.assertEqual(
            auth_service.login_attempts_store, {}
        )  # nothing kept per process
        auth_service.clear_login_throttle(ip)
        self.assertTrue(auth_service.check_login_throttle(ip))
