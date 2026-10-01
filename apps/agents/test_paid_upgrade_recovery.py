"""Audit 2026-10-01 F-06: recovery returned True as soon as the agent had any
earlier payment, so a paid upgrade whose callback and webhook were both lost
was never activated (admin Verify said "already activated")."""
import json
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import RequestFactory, TestCase

from apps.agents.models import Agent, AgentSubscription

PAID_ORDER = 'order_UPGOLD00000001'
UPGRADE_ORDER = 'order_UPGNEW00000002'
UPGRADE_PAY = 'pay_UPGNEW000000002'


def _client(paid_orders):
    client = MagicMock()
    client.order.payments.side_effect = lambda oid: {'items': paid_orders.get(oid, [])}
    client.payment.all.return_value = {'items': [
        {'id': p['id'], 'order_id': oid, 'status': 'captured', 'amount': p['amount']}
        for oid, ps in paid_orders.items() for p in ps]}
    return client


class PaidUpgradeRecoveryTests(TestCase):
    def setUp(self):
        self.agent = Agent.objects.create(fullname='Up', email='upgrade@example.com', mobile='9000000041',
                                          status='active', plan_type='starter')
        AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Starter's Plan", registration_amount='1999.00',
            payment_status='completed', status='active',
            razorpay_order_id=PAID_ORDER, razorpay_payment_id='pay_UPGOLD000000001')
        self.upgrade = AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Professional's Plan", registration_amount='4999.00',
            payment_status='pending', status='inactive', razorpay_order_id=UPGRADE_ORDER)

    def _paid(self):
        return {UPGRADE_ORDER: [{'id': UPGRADE_PAY, 'status': 'captured', 'amount': 499900}]}

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_default_call_stays_cheap_for_paid_agents(self, _q):
        from apps.agents.views.registration import verify_and_activate_pending_payment
        client = _client(self._paid())
        with patch('apps.agents.views.registration.razorpay_client', return_value=client):
            self.assertTrue(verify_and_activate_pending_payment(self.agent))
        client.order.payments.assert_not_called()  # login/dashboard: no Razorpay call
        self.upgrade.refresh_from_db()
        self.assertEqual(self.upgrade.payment_status, 'pending')

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_include_paid_agents_activates_the_upgrade(self, _q):
        from apps.agents.views.registration import verify_and_activate_pending_payment
        with patch('apps.agents.views.registration.razorpay_client', return_value=_client(self._paid())):
            self.assertTrue(verify_and_activate_pending_payment(self.agent, include_paid_agents=True))
        self.upgrade.refresh_from_db()
        self.agent.refresh_from_db()
        self.assertEqual(self.upgrade.payment_status, 'completed')
        self.assertEqual((self.agent.status, self.agent.plan_type), ('active', 'professional'))

    def _admin_verify(self, client):
        from apps.admin_panel.views.agents import admin_verify_pending_payment
        request = RequestFactory().post('/admin/agents/verify-payment/',
                                        data=json.dumps({'agent_id': self.agent.pk}),
                                        content_type='application/json')
        request._dont_enforce_csrf_checks = True
        with patch('apps.admin_panel.views.agents._get_admin_from_session', return_value=1), \
             patch('apps.agents.views.registration.razorpay_client', return_value=client):
            return json.loads(admin_verify_pending_payment(request).content)

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_admin_verify_activates_paid_upgrade(self, _q):
        body = self._admin_verify(_client(self._paid()))
        self.assertTrue(body['success'], body)
        self.assertNotIn('already_active', body)
        self.upgrade.refresh_from_db()
        self.assertEqual(self.upgrade.payment_status, 'completed')

    def test_admin_verify_unpaid_newer_order_says_already_active(self):
        body = self._admin_verify(_client({}))
        self.assertTrue(body['success'], body)
        self.assertTrue(body.get('already_active'))
        self.upgrade.refresh_from_db()
        self.assertEqual(self.upgrade.payment_status, 'pending')

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_backfill_command_activates_upgrade_not_marked_double_charge(self, _q):
        client = _client(self._paid())
        with patch('apps.agents.services.razorpay_checkout.razorpay_client', return_value=client), \
             patch('apps.agents.views.registration.razorpay_client', return_value=client):
            out = StringIO()
            call_command('recover_orphaned_payments', '--days', '7', '--apply', stdout=out)
        self.assertIn('UPGRADE starter -> professional', out.getvalue())
        self.assertNotIn('DOUBLE CHARGE', out.getvalue())
        self.upgrade.refresh_from_db()
        self.assertEqual(self.upgrade.payment_status, 'completed')

    def test_backfill_command_still_flags_same_plan_double_charge(self):
        self.upgrade.selected_plan = "Starter's Plan"
        self.upgrade.save()
        client = _client({UPGRADE_ORDER: [{'id': UPGRADE_PAY, 'status': 'captured', 'amount': 199900}]})
        with patch('apps.agents.services.razorpay_checkout.razorpay_client', return_value=client), \
             patch('apps.agents.views.registration.razorpay_client', return_value=client):
            out = StringIO()
            call_command('recover_orphaned_payments', '--days', '7', '--apply', stdout=out)
        self.assertIn('DOUBLE CHARGE', out.getvalue())
        self.upgrade.refresh_from_db()
        self.assertEqual(self.upgrade.payment_status, 'pending')
