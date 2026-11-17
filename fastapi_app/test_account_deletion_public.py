"""Public Play Console delete flow: DELETE /request-public with email + password."""

import os
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "padosi_agent.settings")
import django

django.setup()

from fastapi import HTTPException

from fastapi_app.routers.account_deletion import request_deletion_public
from fastapi_app.schemas.account_deletion import RequestDeletionPublicSchema


class PublicDeletionRequestTests(unittest.TestCase):
    def _payload(self, **overrides):
        data = {
            "email": "agent@example.com",
            "password": "Secret-123",
            "reason": "Other reason",
            "comments": "",
        }
        data.update(overrides)
        return RequestDeletionPublicSchema(**data)

    def test_unknown_email_gets_generic_error(self):
        db = MagicMock()
        req = MagicMock(headers={})
        with patch(
            "apps.agents.services.account_auth.find_agent", return_value=None
        ):
            with self.assertRaises(HTTPException) as ctx:
                request_deletion_public(self._payload(), req, db)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Email or password is incorrect.")

    def test_wrong_password_gets_same_generic_error(self):
        agent = MagicMock(id=9, email="agent@example.com", mobile="9876543210", user_id=1)
        db = MagicMock()
        req = MagicMock(headers={"user-agent": "test"})
        with (
            patch("apps.agents.services.account_auth.find_agent", return_value=agent),
            patch(
                "apps.agents.services.account_auth.verify_agent_password",
                return_value=(False, None, None),
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                request_deletion_public(self._payload(), req, db)
        self.assertEqual(ctx.exception.detail, "Email or password is incorrect.")

    def test_matching_password_locks_immediately(self):
        agent = MagicMock(
            id=9,
            email="agent@example.com",
            mobile="9876543210",
            user_id=1,
            fullname="Test Agent",
            status="active",
        )
        del_req = MagicMock(
            reference_id="DEL-20261117-ABCDEF0123456789",
            status="COMPLETED",
            scheduled_purge_date=date(2026, 12, 17),
        )
        db = MagicMock()
        req = MagicMock(headers={"user-agent": "test"})
        with (
            patch("apps.agents.services.account_auth.find_agent", return_value=agent),
            patch(
                "apps.agents.services.account_auth.verify_agent_password",
                return_value=(True, None, None),
            ),
            patch(
                "fastapi_app.routers.account_deletion._get_client_ip",
                return_value="203.0.113.10",
            ),
            patch(
                "apps.admin_panel.services.account_deletion_service.lock_account_for_user_deletion",
                return_value=(del_req, True),
            ) as lock,
        ):
            res = request_deletion_public(self._payload(), req, db)
        self.assertTrue(res.success)
        self.assertEqual(res.status, "COMPLETED")
        self.assertEqual(res.reference_id, del_req.reference_id)
        self.assertEqual(res.purge_on, "2026-12-17")
        self.assertIn("locked", res.message.lower())
        lock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
