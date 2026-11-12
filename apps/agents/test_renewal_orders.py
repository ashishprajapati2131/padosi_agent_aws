"""A new renewal checkout must not delete an earlier renewal that already has a Razorpay order
(a late payment on it would be taken but never activate the agent; audit PAY4)."""
from django.test import TestCase
from django.urls import reverse

from apps.agents.models import AgentSubscription
from apps.agents.test_audit_security import _paid_agent


class RenewalOrderTests(TestCase):
    def setUp(self):
        self.agent = _paid_agent()
        self.client.force_login(self.agent.user)

    def _renewals(self):
        return AgentSubscription.objects.filter(agent=self.agent, selected_plan__endswith='(Renewal)')

    def test_second_checkout_keeps_first_order_row(self):
        first = self.client.post(reverse('agents:agent_renew_plan'))
        self.assertEqual(first.status_code, 200, first.content)
        first_order = self._renewals().get().razorpay_order_id
        self.assertTrue(first_order)

        self.client.post(reverse('agents:agent_renew_plan'))

        orders = set(self._renewals().values_list('razorpay_order_id', flat=True))
        self.assertIn(first_order, orders)
        self.assertEqual(len(orders), 2)

    def test_abandoned_row_without_order_is_cleaned(self):
        AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Starter's Plan (Renewal)",
            registration_amount=1, payment_status='pending', status='inactive',
        )
        self.client.post(reverse('agents:agent_renew_plan'))
        self.assertFalse(self._renewals().filter(razorpay_order_id__isnull=True).exists())
        self.assertFalse(self._renewals().filter(razorpay_order_id='').exists())
