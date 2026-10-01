"""Agents cannot change their login email from the edit-profile API."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from fastapi import HTTPException

from fastapi_app.schemas.profile import BasicProfileUpdateRequest
from fastapi_app.services.profile_service import ProfileService


def _basic_payload(email):
    return BasicProfileUpdateRequest(
        agent={"fullname": "New Name", "email": email, "mobile": "9876543210"},
        profile={
            "display_name": "New",
            "whatsapp": "9876543210",
            "languages": "hindi",
            "address": "Ahmedabad",
        },
    )


class ProfileEmailLockTests(SimpleTestCase):
    def _service(self, agent):
        repo = MagicMock()
        repo.get_agent_with_full_profile.return_value = agent
        return ProfileService(repo), repo

    def test_a_different_email_is_rejected_and_nothing_else_is_saved(self):
        agent = SimpleNamespace(
            id=1,
            email="keep@example.com",
            fullname="Old Name",
            mobile="9000000000",
            profile=SimpleNamespace(),
        )
        service, repo = self._service(agent)
        with patch("fastapi_app.services.profile_service.LockUnlockService"):
            with self.assertRaises(HTTPException) as caught:
                service.update_basic_profile(1, _basic_payload("other@example.com"))
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(caught.exception.detail, "Email cannot be changed.")
        self.assertEqual(agent.email, "keep@example.com")
        self.assertEqual(agent.fullname, "Old Name")
        self.assertEqual(agent.mobile, "9000000000")
        repo.db.commit.assert_not_called()

    def test_the_same_email_still_saves_the_other_basic_fields(self):
        profile = SimpleNamespace(
            display_name="",
            whatsapp="",
            languages="",
            address="",
            date_of_birth=None,
        )
        agent = SimpleNamespace(
            id=1,
            email="keep@example.com",
            fullname="Old Name",
            mobile="9000000000",
            profile=profile,
            status="active",
        )
        service, repo = self._service(agent)
        with patch("fastapi_app.services.profile_service.LockUnlockService"), \
                patch.object(service, "_sync_login_identity") as sync, \
                patch.object(service, "_mark_pending_approval"), \
                patch.object(service, "get_profile", return_value={"success": True}):
            result = service.update_basic_profile(1, _basic_payload("Keep@example.com"))
        self.assertEqual(result, {"success": True})
        self.assertEqual(agent.email, "keep@example.com")
        self.assertEqual(agent.fullname, "New Name")
        self.assertEqual(agent.mobile, "9876543210")
        self.assertEqual(profile.languages, "hindi")
        sync.assert_called_once_with(repo.db, "keep@example.com", "keep@example.com", "New Name")
        repo.db.commit.assert_called_once()
