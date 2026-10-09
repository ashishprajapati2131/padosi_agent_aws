"""
Tests for the three new admin modules:
  #16 App Version Control, #15 Session & Device Management, #8 Support Tickets.

Run: python manage.py test apps.admin_panel.test_new_admin_modules
"""
import datetime
import json
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from apps.admin_panel.models.admin_auth import Admin
from apps.admin_panel.models.app_version import AppVersion
from apps.admin_panel.models.user_session import UserSession
from apps.admin_panel.models.contact_submission import ContactSubmission
from apps.admin_panel.models.contact_reply import ContactReply


# ─────────────────────────── #16 App Version ────────────────────────────────
class AppVersionTests(TestCase):
    def setUp(self):
        self.admin = Admin.objects.create(name='Super', email='v@example.com', password='x', role='super')

    def _post(self, data):
        from apps.admin_panel.views.app_version import app_version_save
        req = RequestFactory().post('/admin/app-version/save/', data)
        req.session = {}
        req._messages = _DummyMessages()
        with patch('apps.admin_panel.views.app_version._get_admin_from_session', return_value=self.admin.pk):
            return app_version_save(req)

    def test_create_and_update(self):
        self._post({'platform': 'android', 'latest_version': '1.4.0',
                    'min_supported_version': '1.2.0', 'force_update': '1', 'is_active': '1'})
        row = AppVersion.objects.get(platform='android')
        self.assertEqual(row.latest_version, '1.4.0')
        self.assertTrue(row.force_update)
        # Update same platform (no duplicate row)
        self._post({'platform': 'android', 'latest_version': '1.5.0',
                    'min_supported_version': '1.3.0', 'is_active': '1'})
        self.assertEqual(AppVersion.objects.filter(platform='android').count(), 1)
        row.refresh_from_db()
        self.assertEqual(row.latest_version, '1.5.0')
        self.assertFalse(row.force_update)

    def test_rejects_latest_below_min(self):
        self._post({'platform': 'android', 'latest_version': '1.0.0',
                    'min_supported_version': '2.0.0', 'is_active': '1'})
        self.assertFalse(AppVersion.objects.filter(platform='android').exists())

    def test_rejects_bad_version(self):
        self._post({'platform': 'ios', 'latest_version': 'abc',
                    'min_supported_version': '1.0.0', 'is_active': '1'})
        self.assertFalse(AppVersion.objects.filter(platform='ios').exists())

    def test_rejects_bad_platform(self):
        self._post({'platform': 'windows', 'latest_version': '1.0.0',
                    'min_supported_version': '1.0.0', 'is_active': '1'})
        self.assertEqual(AppVersion.objects.count(), 0)


class AppVersionComparatorTests(TestCase):
    def test_comparator(self):
        from fastapi_app.services.app_version_service import _compare
        self.assertEqual(_compare('1.2.0', '1.2.0'), 0)
        self.assertEqual(_compare('1.1.9', '1.2.0'), -1)
        self.assertEqual(_compare('2.0', '1.9.9'), 1)
        self.assertEqual(_compare('1.2', '1.2.0'), 0)


# ─────────────────────── #15 Session Management ─────────────────────────────
class SessionManagementTests(TestCase):
    def setUp(self):
        self.admin = Admin.objects.create(name='Super', email='s@example.com', password='x', role='super')
        now = datetime.datetime.now()
        self.active = UserSession.objects.create(
            session_token='tok_active', admin_id=self.admin.pk, ip_address='1.2.3.4',
            user_agent='Mozilla/5.0 (Windows NT 10.0) Chrome/120', last_activity=now,
            expires_at=now + datetime.timedelta(days=5), created_at=now, updated_at=now)
        self.expired = UserSession.objects.create(
            session_token='tok_expired', admin_id=self.admin.pk, ip_address='5.6.7.8',
            user_agent='okhttp/4', last_activity=now - datetime.timedelta(days=10),
            expires_at=now - datetime.timedelta(days=1), created_at=now, updated_at=now)

    def test_index_lists_sessions(self):
        from apps.admin_panel.views.sessions import sessions_index
        req = RequestFactory().get('/admin/sessions/')
        req.session = {}
        with patch('apps.admin_panel.views.sessions._get_admin_from_session', return_value=self.admin.pk):
            resp = sessions_index(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'1.2.3.4', resp.content)

    def test_revoke_deletes_session(self):
        from apps.admin_panel.views.sessions import sessions_revoke
        req = RequestFactory().post('/admin/sessions/revoke/', {'id': self.expired.pk})
        req.session = {}
        with patch('apps.admin_panel.views.sessions._get_admin_from_session', return_value=self.admin.pk):
            resp = sessions_revoke(req)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(json.loads(resp.content)['success'])
        self.assertFalse(UserSession.objects.filter(pk=self.expired.pk).exists())
        self.assertTrue(UserSession.objects.filter(pk=self.active.pk).exists())

    def test_revoke_requires_auth(self):
        from apps.admin_panel.views.sessions import sessions_revoke
        req = RequestFactory().post('/admin/sessions/revoke/', {'id': self.active.pk})
        req.session = {}
        with patch('apps.admin_panel.views.sessions._get_admin_from_session', return_value=None):
            resp = sessions_revoke(req)
        self.assertEqual(resp.status_code, 401)
        self.assertTrue(UserSession.objects.filter(pk=self.active.pk).exists())


# ───────────────────────── #8 Support Tickets ──────────────────────────────
class SupportTicketTests(TestCase):
    def setUp(self):
        self.admin = Admin.objects.create(name='Agent Smith', email='t@example.com', password='x', role='super')
        self.ticket = ContactSubmission.objects.create(
            name='Cust', email='cust@example.com', mobile='9000000001',
            subject='Need help', message='Something broke', status='pending')

    _UNSET = object()

    def _call(self, view_path, data, admin_pk=_UNSET):
        module = __import__('apps.admin_panel.views.contacts', fromlist=['x'])
        view = getattr(module, view_path)
        req = RequestFactory().post('/admin/contacts/x/', data)
        req.session = {}
        return_value = self.admin.pk if admin_pk is self._UNSET else admin_pk
        with patch('apps.admin_panel.views.contacts._get_admin_from_session',
                   return_value=return_value):
            return view(req)

    def test_assign(self):
        resp = self._call('contacts_assign', {'id': self.ticket.pk, 'admin_id': self.admin.pk})
        self.assertEqual(resp.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assigned_admin_id, self.admin.pk)

    def test_unassign(self):
        self.ticket.assigned_admin_id = self.admin.pk
        self.ticket.save(update_fields=['assigned_admin_id'])
        resp = self._call('contacts_assign', {'id': self.ticket.pk, 'admin_id': ''})
        self.assertEqual(resp.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.assigned_admin_id)

    def test_priority(self):
        resp = self._call('contacts_set_priority', {'id': self.ticket.pk, 'priority': 'urgent'})
        self.assertEqual(resp.status_code, 200)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.priority, 'urgent')

    def test_bad_priority_rejected(self):
        resp = self._call('contacts_set_priority', {'id': self.ticket.pk, 'priority': 'nuclear'})
        self.assertEqual(resp.status_code, 400)

    def test_internal_note_does_not_email(self):
        with patch('apps.agents.services.brevo.email_service.send_generic') as m:
            resp = self._call('contacts_reply',
                              {'id': self.ticket.pk, 'message': 'private note',
                               'is_internal_note': '1', 'send_email': '1'})
        self.assertEqual(resp.status_code, 200)
        m.assert_not_called()
        r = ContactReply.objects.get(submission=self.ticket)
        self.assertTrue(r.is_internal_note)
        self.assertFalse(r.emailed)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'pending')  # internal note keeps status

    def test_customer_reply_emails_and_sets_replied(self):
        with patch('apps.agents.services.brevo.email_service.send_generic', return_value=True) as m:
            resp = self._call('contacts_reply',
                              {'id': self.ticket.pk, 'message': 'we fixed it',
                               'is_internal_note': '0', 'send_email': '1'})
        self.assertEqual(resp.status_code, 200)
        m.assert_called_once()
        r = ContactReply.objects.get(submission=self.ticket, is_internal_note=False)
        self.assertTrue(r.emailed)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'replied')
        self.assertIsNotNone(self.ticket.last_reply_at)

    def test_reply_email_failure_still_saves(self):
        with patch('apps.agents.services.brevo.email_service.send_generic', side_effect=Exception('smtp down')):
            resp = self._call('contacts_reply',
                              {'id': self.ticket.pk, 'message': 'try',
                               'is_internal_note': '0', 'send_email': '1'})
        self.assertEqual(resp.status_code, 200)
        r = ContactReply.objects.get(submission=self.ticket)
        self.assertFalse(r.emailed)  # email failed but reply saved

    def test_empty_message_rejected(self):
        resp = self._call('contacts_reply', {'id': self.ticket.pk, 'message': '  '})
        self.assertEqual(resp.status_code, 400)

    def test_reply_requires_auth(self):
        resp = self._call('contacts_reply', {'id': self.ticket.pk, 'message': 'hi'}, admin_pk=None)
        self.assertEqual(resp.status_code, 401)


class _DummyMessages:
    """Minimal messages storage so django.contrib.messages works under RequestFactory."""
    def __init__(self):
        self.store = []

    def add(self, level, message, extra_tags=''):
        self.store.append((level, message))
