"""Logged-in DELETE /request: JWT (get_current_user) + password → immediate lock."""

import os
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "padosi_agent.settings")
import django

django.setup()

from fastapi import HTTPException

from fastapi_app.routers.account_deletion import (
    _django_agent_from_jwt_user,
    request_deletion_with_password,
)
from fastapi_app.schemas.account_deletion import RequestDeletionByPasswordSchema


class JwtAgentResolveTests(unittest.TestCase):
    def test_resolves_agent_by_jwt_user_email(self):
        user = MagicMock(id=11, email="a@example.com")
        agent = MagicMock(id=3, email="a@example.com")
        with patch(
            "apps.agents.services.account_auth.find_agent", return_value=agent
        ):
            self.assertIs(agent, _django_agent_from_jwt_user(user))

    def test_missing_agent_is_404(self):
        user = MagicMock(id=11, email="gone@example.com")
        with (
            patch("apps.agents.services.account_auth.find_agent", return_value=None),
            patch(
                "apps.agents.models.Agent.objects.filter"
            ) as flt,
        ):
            flt.return_value.first.return_value = None
            with self.assertRaises(HTTPException) as ctx:
                _django_agent_from_jwt_user(user)
        self.assertEqual(ctx.exception.status_code, 404)


class LoggedInDeletionLockTests(unittest.TestCase):
    def test_wrong_password_rejects(self):
        agent = MagicMock(id=3, email="a@example.com")
        user = MagicMock(id=11, email="a@example.com")
        db = MagicMock()
        req = MagicMock(headers={})
        payload = RequestDeletionByPasswordSchema(password="bad")
        with (
            patch(
                "fastapi_app.routers.account_deletion._django_agent_from_jwt_user",
                return_value=agent,
            ),
            patch(
                "apps.agents.services.account_auth.verify_agent_password",
                return_value=(False, None, None),
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                request_deletion_with_password(payload, req, user, db)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Password is incorrect.")

    def test_ok_password_locks_and_returns_purge_date(self):
        agent = MagicMock(id=3, email="a@example.com")
        user = MagicMock(id=11, email="a@example.com")
        del_req = MagicMock(
            reference_id="DEL-TEST-1",
            status="COMPLETED",
            scheduled_purge_date=date(2026, 12, 20),
        )
        db = MagicMock()
        req = MagicMock(headers={"user-agent": "app"})
        payload = RequestDeletionByPasswordSchema(password="ok", reason="Leaving")
        with (
            patch(
                "fastapi_app.routers.account_deletion._django_agent_from_jwt_user",
                return_value=agent,
            ),
            patch(
                "apps.agents.services.account_auth.verify_agent_password",
                return_value=(True, None, None),
            ),
            patch(
                "fastapi_app.routers.account_deletion._get_client_ip",
                return_value="127.0.0.1",
            ),
            patch(
                "apps.admin_panel.services.account_deletion_service.lock_account_for_user_deletion",
                return_value=(del_req, True),
            ),
        ):
            res = request_deletion_with_password(payload, req, user, db)
        self.assertTrue(res.success)
        self.assertEqual(res.status, "COMPLETED")
        self.assertEqual(res.purge_on, "2026-12-20")


if __name__ == "__main__":
    unittest.main()
