"""Audit 2026-10-01 F-22: refunding an upgrade revoked only the upgrade row;
the agent kept the upgraded plan_type (the earlier subscription had been
deactivated as superseded) and the referrer lost the credit of the original
payment that still stands."""
from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase

from apps.agents.models import Agent, AgentSubscription


class UpgradeRefundTests(TestCase):
    def setUp(self):
        self.agent = Agent.objects.create(fullname='Up', email='refund.up@example.com', mobile='9000000191',
                                          status='active', plan_type='professional')
        self.starter = AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Starter's Plan", registration_amount='2359.00',
            payment_status='completed', status='inactive', starts_at=datetime.now() - timedelta(days=30),
            razorpay_order_id='order_STARTER000001', razorpay_payment_id='pay_STARTER0000001')
        self.upgrade = AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Professional's Plan", registration_amount='8258.00',
            payment_status='completed', status='active', starts_at=datetime.now(),
            razorpay_order_id='order_UPGRADE000001', razorpay_payment_id='pay_UPGRADE0000001')

    def _refund(self, sub, amount):
        from apps.agents.views.registration import _handle_refund_webhook
        event = {'event': 'refund.processed', 'payload': {'payment': {'entity': {
            'id': sub.razorpay_payment_id, 'order_id': sub.razorpay_order_id,
            'amount': amount, 'amount_refunded': amount, 'refund_status': 'full'}}}}
        with patch('apps.referral_championship.services.qualification_service.revert_championship_qualification') as champ, \
             patch('apps.event_referral.services.qualification_service.revert_event_referral') as event_rev:
            self.assertEqual(_handle_refund_webhook(event).status_code, 200)
        return champ, event_rev

    def test_refunded_upgrade_returns_to_the_paid_plan(self):
        champ, event_rev = self._refund(self.upgrade, 825800)
        self.agent.refresh_from_db()
        self.starter.refresh_from_db()
        self.assertEqual((self.agent.status, self.agent.plan_type), ('active', 'starter'))
        self.assertEqual(self.starter.status, 'active')
        champ.assert_not_called()       # the original payment's referral credit stands
        event_rev.assert_not_called()

    def test_refund_of_the_only_payment_still_revokes_and_reverts_credit(self):
        self.starter.delete()
        champ, _ = self._refund(self.upgrade, 825800)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, 'pending_payment')
        champ.assert_called_once()
