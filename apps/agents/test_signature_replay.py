"""A Razorpay signature is a one-time, short-lived login, and replaying an old order never
downgrades the agent (audit PAY2/PAY3)."""
import datetime
import json
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from apps.agents.models import AgentSubscription
from apps.agents.test_audit_security import _paid_agent

VALID = 'apps.agents.views.registration._payer_signature_valid'


class SignatureReplayTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = _paid_agent()
        self.sub = self.agent.subscriptions.first()

    def _verify(self, client, order_id):
        return client.post(
            reverse('agents:agent_register_verify_payment'),
            data=json.dumps({
                'razorpay_order_id': order_id,
                'razorpay_payment_id': 'pay_X',
                'razorpay_signature': 'sig',
            }),
            content_type='application/json',
        )

    @patch(VALID, return_value=True)
    def test_signature_logs_in_once_only(self, _valid):
        first, second = Client(), Client()
        self._verify(first, self.sub.razorpay_order_id)
        self.assertIn('_auth_user_id', first.session)

        self._verify(second, self.sub.razorpay_order_id)
        self.assertNotIn('_auth_user_id', second.session)

    @patch(VALID, return_value=True)
    def test_signature_of_old_order_does_not_log_in(self, _valid):
        AgentSubscription.objects.filter(pk=self.sub.pk).update(
            created_at=datetime.datetime.now() - datetime.timedelta(days=3)
        )
        self._verify(self.client, self.sub.razorpay_order_id)
        self.assertNotIn('_auth_user_id', self.client.session)

    @patch(VALID, return_value=True)
    def test_replaying_old_order_keeps_newer_plan(self, _valid):
        newer = AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Professional's Plan",
            registration_amount=Decimal('9999.00'), payment_status='completed', status='active',
            razorpay_order_id='order_NEWER1', razorpay_payment_id='pay_NEWER1',
        )
        self.agent.plan_type = 'professional'
        self.agent.save(update_fields=['plan_type'])

        self._verify(self.client, self.sub.razorpay_order_id)

        self.agent.refresh_from_db()
        newer.refresh_from_db()
        self.assertEqual(self.agent.plan_type, 'professional')
        self.assertEqual(newer.status, 'active')
