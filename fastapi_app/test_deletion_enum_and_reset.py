"""Audit API3 + API4:
- Reset-password with an unknown email returns the same generic error as a bad token.
- In-app password change revokes every other UserToken but keeps the caller's JWT alive.
"""

import unittest
from unittest.mock import MagicMock, patch

from fastapi_app.services.password_reset_service import PasswordResetService


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
