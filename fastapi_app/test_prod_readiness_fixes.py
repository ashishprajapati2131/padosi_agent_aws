"""Production-readiness fixes: forgot-password throttle + no account enumeration."""

import asyncio
import json
import unittest
from unittest.mock import MagicMock

from django.core.cache import cache

from fastapi_app.schemas.auth import ForgotPasswordRequest
from fastapi_app.services.password_reset_service import PasswordResetService


def _forgot(email, user=None):
    service = PasswordResetService(MagicMock())
    service.user_repo = MagicMock()
    service.user_repo.get_by_email.return_value = user
    req = MagicMock()
    req.client.host = "203.0.113.9"
    req.headers = {}
    return asyncio.run(
        service.send_reset_link(
            ForgotPasswordRequest(email=email, login_type="agent"), req
        )
    )


class ForgotPasswordTests(unittest.TestCase):
    def setUp(self):
        cache.clear()

    def test_unknown_and_wrong_role_get_the_same_generic_answer(self):
        unknown = _forgot("nobody.fp@example.com")
        distributor = _forgot("dist.fp@example.com", user=MagicMock(role="distributor"))
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(unknown.body, distributor.body)
        self.assertTrue(json.loads(unknown.body)["success"])

    def test_fourth_request_per_email_within_an_hour_is_throttled(self):
        codes = [_forgot("limit.fp@example.com").status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])


if __name__ == "__main__":
    unittest.main()
