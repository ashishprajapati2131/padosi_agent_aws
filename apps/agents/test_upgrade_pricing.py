"""Audit 2026-10-01 F-10: the web upgrade charged the trial discount to every
agent (less than the price shown), crashed on any promo code, and allowed
buying a lower plan."""
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.agents.models import Agent, AgentSubscription, PromoCode
from apps.home.models import SiteSetting


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class UpgradePricingTests(TestCase):
    def setUp(self):
        SiteSetting.set_value('pricing_config', {
            'starter': {'name': "Starter's Plan", 'full_price': 2359},
            'professional': {'name': "Professional's Plan", 'full_price': 8258},
        }, 'pricing')
        SiteSetting.set_value('trial_upgrade_discount', 20, 'pricing')
        self.user = User.objects.create_user('upg', 'upg@example.com', 'x')
        self.agent = Agent.objects.create(user=self.user, fullname='Upg', email='upg@example.com',
                                          mobile='9000000051', status='active', plan_type='starter')
        AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Starter's Plan", registration_amount='2359.00',
            payment_status='completed', status='active',
            razorpay_order_id='order_UPGPRICE000001', razorpay_payment_id='pay_UPGPRICE0000001')
        self.client.force_login(self.user)

    def _upgrade(self, plan='professional', **extra):
        with patch('apps.agents.services.razorpay_checkout.create_checkout_order',
                   return_value=('order_UPGPRICE000002', False)) as create:
            resp = self.client.post('/agent/upgrade-plan/', data=json.dumps({'plan_type': plan, **extra}),
                                    content_type='application/json')
        amount = create.call_args.args[0] if create.called else None
        return resp, amount

    def test_paid_agent_is_charged_the_displayed_full_price(self):
        resp, amount = self._upgrade()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(amount, 825800)  # dashboard shows the full price to non-trial agents

    def test_trial_agent_still_gets_the_trial_discount(self):
        self.agent.plan_type = 'free_trial'
        self.agent.trial_ends_at = timezone.now() + timedelta(days=10)
        self.agent.save()
        resp, amount = self._upgrade()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(amount, 660600)  # 20% off, same as the dashboard

    def test_promo_code_no_longer_crashes_and_applies(self):
        PromoCode.objects.create(code='UP10', discount_type='percentage', discount_value=10,
                                 is_active=True, applicable_plan='all')
        resp, amount = self._upgrade(promo_code='UP10')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json().get('success', True), resp.json())
        self.assertEqual(amount, 743200)  # 8258 - 10% = 7432.2 -> 7432

    def test_lower_or_same_plan_is_refused(self):
        self.agent.plan_type = 'professional'
        self.agent.save()
        resp, amount = self._upgrade(plan='starter')
        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(amount)
        resp, amount = self._upgrade(plan='professional')
        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(amount)
