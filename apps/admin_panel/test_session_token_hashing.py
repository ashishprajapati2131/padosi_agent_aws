"""Audit 2026-11-07 S13: user_sessions stores SHA-256 of the admin cookie, never the cookie.
Plaintext rows from before the change keep working and are upgraded on first use."""
import hashlib
from datetime import datetime, timedelta

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.admin_panel.auth import _resolve_admin_from_session, hash_session_token
from apps.admin_panel.models.admin_auth import Admin
from apps.admin_panel.models.user_session import UserSession, UserSessionData


def _request(cookie=None):
    request = RequestFactory().get("/admin/dashboard/")
    if cookie:
        request.COOKIES["session_token"] = cookie
    SessionMiddleware(lambda r: None).process_request(request)
    request._messages = FallbackStorage(request)
    return request


class SessionTokenHashingTests(TestCase):
    def setUp(self):
        self.admin = Admin.objects.create(name="H", email="hash@example.com", password="x", role="super")

    def test_new_session_stores_only_the_hash(self):
        from apps.admin_panel.views.dashboard import _issue_admin_session
        response = _issue_admin_session(_request(), self.admin.pk, self.admin.email)
        cookie = response.cookies["session_token"].value
        stored = UserSession.objects.get(admin_id=self.admin.pk).session_token
        self.assertEqual(stored, "sha256$" + hashlib.sha256(cookie.encode()).hexdigest())
        self.assertNotEqual(stored, cookie)
        self.assertEqual(_resolve_admin_from_session(_request(cookie)), self.admin.pk)

    def test_legacy_plaintext_session_works_and_is_upgraded(self):
        now = datetime.now()
        row = UserSession.objects.create(session_token="legacy-raw-token", admin_id=self.admin.pk,
                                         last_activity=now, expires_at=now + timedelta(days=1), created_at=now)
        UserSessionData.objects.create(session=row, data_key="admin_id", data_value=str(self.admin.pk))
        self.assertEqual(_resolve_admin_from_session(_request("legacy-raw-token")), self.admin.pk)
        row.refresh_from_db()
        self.assertEqual(row.session_token, hash_session_token("legacy-raw-token"))
        self.assertEqual(_resolve_admin_from_session(_request("legacy-raw-token")), self.admin.pk)

    def test_the_stored_hash_is_not_a_valid_cookie(self):
        from apps.admin_panel.views.dashboard import _issue_admin_session
        _issue_admin_session(_request(), self.admin.pk, self.admin.email)
        stored = UserSession.objects.get(admin_id=self.admin.pk).session_token
        self.assertIsNone(_resolve_admin_from_session(_request(stored)))
