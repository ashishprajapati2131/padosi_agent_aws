"""Audit 2026-10-01 F-23: admin activity log rows had a NULL admin (it read
session['admin_id'], which admin login never sets) and a log failure could
break the admin action."""
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from apps.admin_panel.models import AdminActivityLog


class ActivityLogAttributionTests(TestCase):
    def _request(self):
        request = RequestFactory().post('/admin/x/', REMOTE_ADDR='203.0.113.9')
        request.session = {}
        return request

    def test_admin_comes_from_the_session_token(self):
        with patch('apps.admin_panel.views.dashboard._get_admin_from_session', return_value=42):
            row = AdminActivityLog.log('Did something', 'Agent', 7, request=self._request())
        self.assertEqual((row.admin_id, row.model_id, row.ip_address), (42, 7, '203.0.113.9'))

    def test_explicit_admin_id_wins(self):
        row = AdminActivityLog.log('Did something', request=self._request(), admin_id=5)
        self.assertEqual(row.admin_id, 5)

    def test_logging_failure_never_raises(self):
        with patch.object(AdminActivityLog.objects, 'create', side_effect=Exception('no such column: action')):
            self.assertIsNone(AdminActivityLog.log('Did something', request=self._request(), admin_id=1))

    def test_spoofed_forwarded_for_is_not_trusted(self):
        request = RequestFactory().post('/admin/x/', REMOTE_ADDR='198.51.100.20', HTTP_X_FORWARDED_FOR='1.2.3.4')
        request.session = {}
        row = AdminActivityLog.log('Did something', request=request, admin_id=1)
        self.assertEqual(row.ip_address, '198.51.100.20')
