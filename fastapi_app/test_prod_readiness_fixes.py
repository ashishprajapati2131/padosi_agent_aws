"""Production-readiness fixes: forgot-password throttle + no account enumeration,
and account-deletion OTP expiry enforcement."""

import asyncio
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from fastapi import HTTPException

from fastapi_app.routers.account_deletion import _hash_otp, verify_deletion_otp
from fastapi_app.schemas.account_deletion import VerifyDeletionOtpSchema
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


class DeletionOtpExpiryTests(unittest.TestCase):
    def _verify(self, expires_at):
        del_req = MagicMock(
            is_verified=False,
            reference_id="DEL-12345",
            data_retention_summary={
                "otp_attempts": 0,
                "otp_hash": _hash_otp("123456"),
                "otp_expires_at": expires_at,
            },
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = del_req
        payload = VerifyDeletionOtpSchema(
            reference_id="DEL-12345", email="del@example.com", otp="123456"
        )
        verify_deletion_otp(payload, MagicMock(), db)
        return del_req

    def test_expired_otp_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            self._verify((datetime.utcnow() - timedelta(minutes=1)).isoformat())
        self.assertIn("expired", ctx.exception.detail)

    def test_unparseable_expiry_counts_as_expired(self):
        with self.assertRaises(HTTPException):
            self._verify("not-a-date")

    def test_valid_otp_is_accepted(self):
        del_req = self._verify((datetime.utcnow() + timedelta(minutes=5)).isoformat())
        self.assertTrue(del_req.is_verified)


if __name__ == "__main__":
    unittest.main()
