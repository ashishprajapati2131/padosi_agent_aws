"""Audit 2026-10-01 F-04 / F-13: admin payment reconcile.

It used to resolve the agent by the payer's email (creating a ghost agent and
moving the real registrant's subscription and invoice to it), invent payment
ids, take the plan from the request without an amount check, accept
test-mode/authorized payments, demote active agents and render Razorpay/DB
values with innerHTML.
"""
import json
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, TestCase

from apps.agents.models import Agent, AgentDraft, AgentSubscription

ORDER = 'order_RECONCILE00001'
PAY = 'pay_RECONCILE000001'


def _client(payment=None, order=None, order_payments=None):
    client = MagicMock()
    if payment is None:
        client.payment.fetch.side_effect = Exception('not found')
    else:
        client.payment.fetch.return_value = payment
    client.order.fetch.return_value = order or {'id': ORDER, 'receipt': 'agent_draft_0_1', 'status': 'paid'}
    client.order.payments.return_value = {'items': order_payments or []}
    return client


def _captured(amount=235900, email='someone.else@example.com'):
    return {'id': PAY, 'order_id': ORDER, 'status': 'captured', 'amount': amount, 'email': email, 'notes': {}}


class ReconcileExecuteTests(TestCase):
    def setUp(self):
        self.agent = Agent.objects.create(fullname='Real Registrant', email='registrant@example.com',
                                          mobile='9000000091', status='pending_payment', plan_type='starter')
        self.sub = AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Starter's Plan", registration_amount='2359.00',
            payment_status='pending', status='inactive', razorpay_order_id=ORDER)

    def _execute(self, client, **body):
        from apps.admin_panel.views.payment_reconcile import reconcile_execute_payment
        payload = {'payment_id': PAY, 'order_id': ORDER, 'email': 'someone.else@example.com',
                   'plan_type': 'exclusive'}
        payload.update(body)
        request = RequestFactory().post('/admin/payments/reconcile/execute/', data=json.dumps(payload),
                                        content_type='application/json')
        request.session = {}
        with patch('apps.admin_panel.views.payment_reconcile._is_admin_authenticated', return_value=1), \
             patch('apps.admin_panel.views.payment_reconcile._get_razorpay_clients', return_value=[('live', client)]), \
             patch('apps.admin_panel.views.payment_reconcile.fulfill_invoice_and_welcome') as fulfil:
            fulfil.return_value = MagicMock(invoice_number='INV-1', synced_to_sheet=False)
            resp = reconcile_execute_payment(request)
        return json.loads(resp.content), fulfil

    def test_activates_the_orders_own_registrant_not_the_payer(self):
        body, fulfil = self._execute(_client(_captured()))
        self.assertTrue(body['success'], body)
        self.assertEqual(body['agent_id'], self.agent.pk)
        self.sub.refresh_from_db()
        self.agent.refresh_from_db()
        self.assertEqual((self.sub.payment_status, self.sub.razorpay_payment_id), ('completed', PAY))
        self.assertEqual(self.sub.selected_plan, "Starter's Plan")      # not the requested Exclusive
        self.assertEqual((self.agent.status, self.agent.plan_type), ('pending_approval', 'starter'))
        self.assertFalse(Agent.objects.filter(email='someone.else@example.com').exists())
        fulfil.assert_called_once()

    def test_second_run_is_idempotent(self):
        self._execute(_client(_captured()))
        body, fulfil = self._execute(_client(_captured()))
        self.assertTrue(body['success'], body)
        self.assertIn('Already reconciled', body['message'])
        fulfil.assert_not_called()

    def test_authorized_payment_is_refused(self):
        payment = _captured()
        payment['status'] = 'authorized'
        body, fulfil = self._execute(_client(payment))
        self.assertFalse(body['success'])
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.payment_status, 'pending')
        fulfil.assert_not_called()

    def test_paid_order_without_a_payment_is_refused_not_invented(self):
        body, _ = self._execute(_client(None, order_payments=[]), payment_id='')
        self.assertFalse(body['success'])
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.payment_status, 'pending')
        self.assertFalse(AgentSubscription.objects.filter(razorpay_payment_id__startswith='pay_').exists())

    def test_amount_mismatch_is_refused(self):
        body, _ = self._execute(_client(_captured(amount=100)))
        self.assertFalse(body['success'])
        self.assertIn('Amount mismatch', body['message'])

    def test_payment_already_used_elsewhere_is_refused(self):
        other = Agent.objects.create(fullname='Other', email='other.paid@example.com', mobile='9000000092')
        AgentSubscription.objects.create(
            agent=other, selected_plan="Starter's Plan", registration_amount='2359.00',
            payment_status='completed', status='active', razorpay_order_id='order_OTHERORDER0001',
            razorpay_payment_id=PAY)
        body, _ = self._execute(_client(_captured()))
        self.assertFalse(body['success'])
        self.assertIn('already attached', body['message'])

    def test_no_ghost_agent_for_an_unknown_payer(self):
        self.sub.delete()
        client = _client(_captured(email='stranger@example.com'),
                         order={'id': ORDER, 'receipt': 'ins_cart_1', 'status': 'paid'})
        body, _ = self._execute(client, email='stranger@example.com')
        self.assertFalse(body['success'])
        self.assertFalse(Agent.objects.filter(email='stranger@example.com').exists())
        self.assertFalse(AgentDraft.objects.filter(email='stranger@example.com').exists())

    def test_active_agent_upgrade_stays_active(self):
        self.agent.status = 'active'
        self.agent.save()
        AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Starter's Plan", registration_amount='2359.00',
            payment_status='completed', status='active', razorpay_order_id='order_EARLIER000001',
            razorpay_payment_id='pay_EARLIER0000001')
        self.sub.selected_plan, self.sub.registration_amount = "Professional's Plan", '8258.00'
        self.sub.save()
        body, _ = self._execute(_client(_captured(amount=825800)))
        self.assertTrue(body['success'], body)
        self.agent.refresh_from_db()
        self.assertEqual((self.agent.status, self.agent.plan_type), ('active', 'professional'))

    def test_bad_id_format_is_rejected(self):
        body, _ = self._execute(_client(_captured()), payment_id='pay_../../x')
        self.assertFalse(body['success'])
        self.assertIn('format', body['message'])
