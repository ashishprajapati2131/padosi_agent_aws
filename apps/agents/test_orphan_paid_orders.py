"""Audit 2026-10-01 F-02: retrying checkout re-pointed the pending subscription
at the new order, so a payment for the earlier order was never activated."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command

from apps.agents.models import Agent, AgentDraft, AgentSubscription
from apps.agents.signup_test_support import (
    ORDER_A, ORDER_B, PAY_A, _SignupBase, _captured_webhook, _rzp,
)


class RetryCheckoutOrphanOrderTests(_SignupBase):
    """F-02."""

    def test_retry_keeps_one_row_per_order(self):
        agent = self._signup('retry.rows@example.com', [ORDER_A, ORDER_B], plans=['starter', 'professional'])
        a = AgentSubscription.objects.get(razorpay_order_id=ORDER_A)
        b = AgentSubscription.objects.get(razorpay_order_id=ORDER_B)
        self.assertEqual(a.agent_id, agent.pk)
        self.assertEqual(b.agent_id, agent.pk)
        self.assertEqual(a.selected_plan, "Starter's Plan")
        self.assertEqual(b.selected_plan, "Professional's Plan")
        self.assertLess(a.registration_amount, b.registration_amount)

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_webhook_for_earlier_order_activates(self, _q):
        agent = self._signup('retry.webhook@example.com', [ORDER_A, ORDER_B])
        paise = self._paise(AgentSubscription.objects.get(razorpay_order_id=ORDER_A))
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(paise)), \
             patch('apps.agents.views.registration.razorpay_webhook_secret', return_value='whsec'):
            r = self.client.post('/razorpay-webhook/', data=_captured_webhook(ORDER_A, paise),
                                 content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE='sig')
        self.assertEqual(r.status_code, 200, r.content)
        agent.refresh_from_db()
        self.assertEqual(AgentSubscription.objects.get(razorpay_order_id=ORDER_A).payment_status, 'completed')
        self.assertEqual(agent.status, 'pending_approval')

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_approvals_queue_shows_the_paid_order(self, _q):
        """Admin Approvals must show the paid row, not the newer unpaid retry."""
        from django.db import connection
        from apps.admin_panel.views.agents import _build_queue_query
        agent = self._signup('retry.queue@example.com', [ORDER_A, ORDER_B])
        paise = self._paise(AgentSubscription.objects.get(razorpay_order_id=ORDER_A))
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(paise)), \
             patch('apps.agents.views.registration.razorpay_webhook_secret', return_value='whsec'):
            self.client.post('/razorpay-webhook/', data=_captured_webhook(ORDER_A, paise),
                             content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE='sig')
        query, params = _build_queue_query('pending_approval', '', 'All Plans', '', 'All Events', 'newest')
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            cols = [c[0] for c in cursor.description]
            rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        row = next(r for r in rows if r['id'] == agent.pk)
        self.assertEqual((row['razorpay_order_id'], row['sub_payment_status']), (ORDER_A, 'completed'))

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_browser_callback_for_earlier_order_activates(self, _q):
        agent = self._signup('retry.callback@example.com', [ORDER_A, ORDER_B])
        paise = self._paise(AgentSubscription.objects.get(razorpay_order_id=ORDER_A))
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(paise)):
            r = self.client.post('/agent-register/verify-payment/', data={
                'razorpay_order_id': ORDER_A, 'razorpay_payment_id': PAY_A,
                'razorpay_signature': 'sig'}, content_type='application/json')
        self.assertTrue(r.json()['success'], r.json())
        agent.refresh_from_db()
        self.assertEqual(agent.status, 'pending_approval')

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_recovery_checks_earlier_open_orders(self, _q):
        """Login / dashboard / admin Verify use this when callback and webhook were missed."""
        from apps.agents.views.registration import verify_and_activate_pending_payment
        agent = self._signup('retry.recover@example.com', [ORDER_A, ORDER_B])
        paise = self._paise(AgentSubscription.objects.get(razorpay_order_id=ORDER_A))
        paid = {ORDER_A: [{'id': PAY_A, 'status': 'captured', 'amount': paise}]}
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(paise, paid)):
            self.assertTrue(verify_and_activate_pending_payment(agent))
        self.assertEqual(AgentSubscription.objects.get(razorpay_order_id=ORDER_A).payment_status, 'completed')
        self.assertEqual(AgentSubscription.objects.get(razorpay_order_id=ORDER_B).payment_status, 'pending')

    def _legacy_orphan(self, email):
        """Data written by the old code: the only row points at ORDER_B; ORDER_A has none."""
        agent = self._signup(email, [ORDER_B])
        draft = AgentDraft.objects.filter(email=email).first()
        order_a = {'id': ORDER_A, 'amount': 235900, 'receipt': f'agent_draft_{draft.pk}_1',
                   'notes': {'draft_id': str(draft.pk), 'email': email, 'plan_type': 'starter'}}
        return agent, order_a

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_webhook_rebuilds_legacy_orphaned_order(self, _q):
        agent, order_a = self._legacy_orphan('legacy.orphan@example.com')
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(235900, order=order_a)), \
             patch('apps.agents.views.registration.razorpay_webhook_secret', return_value='whsec'):
            r = self.client.post('/razorpay-webhook/', data=_captured_webhook(ORDER_A, 235900),
                                 content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE='sig')
        self.assertEqual(r.status_code, 200, r.content)
        sub = AgentSubscription.objects.get(razorpay_order_id=ORDER_A)
        self.assertEqual((sub.agent_id, sub.payment_status, sub.selected_plan),
                         (agent.pk, 'completed', "Starter's Plan"))
        agent.refresh_from_db()
        self.assertEqual((agent.status, agent.plan_type), ('pending_approval', 'starter'))

    def test_non_registration_order_is_not_adopted(self):
        from apps.agents.views.registration import adopt_orphan_registration_order
        self._signup('other.order@example.com', [ORDER_B])
        insurance_order = {'id': ORDER_A, 'amount': 235900, 'receipt': 'ins_cart_9',
                           'notes': {'email': 'other.order@example.com', 'plan_type': 'starter'}}
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(0, order=insurance_order)):
            self.assertIsNone(adopt_orphan_registration_order(ORDER_A))
        self.assertFalse(AgentSubscription.objects.filter(razorpay_order_id=ORDER_A).exists())

    def test_order_notes_email_must_match_its_draft(self):
        from apps.agents.views.registration import adopt_orphan_registration_order
        _agent, order_a = self._legacy_orphan('owner@example.com')
        Agent.objects.create(fullname='Y', email='someone.else@example.com', mobile='9876543211')
        order_a['notes']['email'] = 'someone.else@example.com'
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(0, order=order_a)):
            self.assertIsNone(adopt_orphan_registration_order(ORDER_A))

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_backfill_command_dry_run_then_apply(self, _q):
        agent, order_a = self._legacy_orphan('backfill@example.com')
        client = _rzp(235900, {ORDER_A: [{'id': PAY_A, 'status': 'captured', 'amount': 235900}]}, order_a)
        client.payment.all.return_value = {'items': [
            {'id': PAY_A, 'order_id': ORDER_A, 'status': 'captured', 'amount': 235900}]}
        with patch('apps.agents.services.razorpay_checkout.razorpay_client', return_value=client), \
             patch('apps.agents.views.registration.razorpay_client', return_value=client):
            out = StringIO()
            call_command('recover_orphaned_payments', '--days', '7', stdout=out)
            self.assertIn('ORPHANED_ORDER', out.getvalue())
            self.assertFalse(AgentSubscription.objects.filter(razorpay_order_id=ORDER_A).exists())

            out = StringIO()
            call_command('recover_orphaned_payments', '--days', '7', '--apply', stdout=out)
            self.assertIn('activated=True', out.getvalue())
        agent.refresh_from_db()
        self.assertEqual(agent.status, 'pending_approval')
        self.assertEqual(AgentSubscription.objects.get(razorpay_order_id=ORDER_A).payment_status, 'completed')
