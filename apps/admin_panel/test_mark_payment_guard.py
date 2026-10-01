"""Audit 2026-10-01 F-14: finance staff could mark any unpaid subscription as
completed (which unlocks the dashboard) with no gateway check."""
import json
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from apps.admin_panel.models.admin_auth import Admin
from apps.agents.models import Agent, AgentSubscription


class MarkPaymentGuardTests(TestCase):
    def setUp(self):
        self.staff = Admin.objects.create(name='Staff', email='staff@example.com', password='x', role='staff')
        self.super = Admin.objects.create(name='Super', email='super@example.com', password='x', role='super')
        agent = Agent.objects.create(fullname='A', email='mark@example.com', mobile='9000000071', status='pending_payment')
        self.sub = AgentSubscription.objects.create(
            agent=agent, selected_plan="Starter's Plan", registration_amount='2359.00',
            payment_status='pending', status='inactive', razorpay_order_id='order_MARKPAY0000001')

    def _mark(self, admin, status):
        from apps.admin_panel.views.finance import mark_payment
        request = RequestFactory().post('/admin/finance/mark-payment/',
                                        {'subscription_id': self.sub.pk, 'status': status},
                                        HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        request.session = {}
        with patch('apps.admin_panel.views.finance._get_admin_from_session', return_value=admin.pk):
            resp = mark_payment(request)
        self.sub.refresh_from_db()
        return resp.status_code, json.loads(resp.content)

    def test_staff_cannot_mark_completed(self):
        code, _ = self._mark(self.staff, 'completed')
        self.assertEqual(code, 403)
        self.assertEqual(self.sub.payment_status, 'pending')

    def test_staff_can_still_mark_failed(self):
        code, body = self._mark(self.staff, 'failed')
        self.assertEqual(code, 200, body)
        self.assertEqual(self.sub.payment_status, 'failed')

    def test_super_admin_marks_completed_with_dates(self):
        code, body = self._mark(self.super, 'completed')
        self.assertEqual(code, 200, body)
        self.assertEqual((self.sub.payment_status, self.sub.status), ('completed', 'active'))
        self.assertIsNotNone(self.sub.starts_at)
        self.assertEqual((self.sub.expires_at - self.sub.starts_at).days, 365)

    def test_staff_cannot_undo_a_completed_payment(self):
        self._mark(self.super, 'completed')
        code, _ = self._mark(self.staff, 'failed')
        self.assertEqual(code, 403)
        self.assertEqual(self.sub.payment_status, 'completed')

    def test_get_is_rejected(self):
        from apps.admin_panel.views.finance import mark_payment
        request = RequestFactory().get('/admin/finance/mark-payment/', {'subscription_id': self.sub.pk, 'status': 'failed'})
        self.assertEqual(mark_payment(request).status_code, 405)
