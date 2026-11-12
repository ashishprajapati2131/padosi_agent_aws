"""Audit API2 + API3 + API4:
- Deletion OTP request gives one generic error for every mismatch (no oracle).
- Reset-password with an unknown email returns the same generic error as a bad token.
- In-app password change revokes every other UserToken but keeps the caller's JWT alive.
"""

import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from fastapi_app.routers.account_deletion import request_deletion_otp
from fastapi_app.services.password_reset_service import PasswordResetService


class DeletionEnumerationTests(unittest.TestCase):
    def _call(self, agent, profile=None):
        payload = MagicMock(
            email="victim@example.com",
            mobile="9876543210",
            pan_number="ABCDE1234F",
            fullname="V",
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [
            agent,
            profile,
            None,
        ]
        with self.assertRaises(HTTPException) as ctx:
            request_deletion_otp(
                payload, MagicMock(client=MagicMock(host="1.1.1.1"), headers={}), db
            )
        return ctx.exception

    def test_unknown_pan_wrong_phone_and_missing_email_share_one_message(self):
        unknown = self._call(None).detail
        bad_pan = self._call(
            MagicMock(id=1, mobile="9876543210"), MagicMock(pan_number="OTHER1234X")
        ).detail
        bad_phone = self._call(
            MagicMock(id=1, mobile="9999999999"), MagicMock(pan_number="ABCDE1234F")
        ).detail
        self.assertEqual(unknown, bad_pan)
        self.assertEqual(unknown, bad_phone)
        for leak in ("PAN", "phone", "not exist", "email"):
            self.assertNotIn(leak, unknown)


class ResetEnumerationTests(unittest.TestCase):
    def test_unknown_email_message_matches_invalid_token(self):
        svc = PasswordResetService(MagicMock())
        svc.user_repo = MagicMock()
        svc.user_repo.get_by_email.return_value = None
        req = MagicMock(email="nobody@example.com", token="abc", current_password=None)
        resp = svc.reset_password(req, req=MagicMock(headers={}), current_agent=None)
        import json

        body = json.loads(resp.body)
        self.assertIn("invalid or has expired", body["message"])
        self.assertNotIn("not registered", body["message"])


class InAppRevocationTests(unittest.TestCase):
    def test_in_app_change_revokes_other_jtis_but_not_current(self):
        svc = PasswordResetService(MagicMock())
        svc.user_repo = MagicMock()
        svc.token_repo = MagicMock()
        agent = MagicMock(email="me@example.com", id=10)
        user = MagicMock(id=10, email="me@example.com", status="active", password="h")
        svc.user_repo.get_by_email.return_value = user
        req_schema = MagicMock(
            email="me@example.com",
            password="Newpw-12345",
            current_password="Old",
            token=None,
        )
        http = MagicMock(headers={"Authorization": "Bearer header.payload.sig"})
        tokens = MagicMock()
        tokens.filter.return_value = tokens
        tokens.update.return_value = None
        svc.db.query.return_value.filter.return_value = tokens
        with (
            patch.object(svc, "_current_password_ok", return_value=True),
            patch(
                "fastapi_app.services.password_reset_service.decode_access_token",
                return_value={"jti": "KEEP-ME"},
            ),
            patch(
                "fastapi_app.services.password_reset_service.get_password_hash",
                return_value="$2b$x",
            ),
            patch(
                "fastapi_app.services.password_reset_service.secrets.token_hex",
                return_value="x" * 60,
            ),
        ):
            svc.reset_password(req_schema, req=http, current_agent=agent)
        tokens.filter.assert_called()
        jti_filter = str(tokens.filter.call_args.args[0])
        self.assertIn("user_tokens.jti", jti_filter)
        self.assertIn("!=", jti_filter)
