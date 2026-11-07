"""Audit 2026-10-01 F-10: the web upgrade charged the trial discount to every
agent (less than the price shown), crashed on any promo code, and allowed
buying a lower plan.

Pricing semantics: pricing_config.full_price is the BASE price excl. GST.
  Starter  base ₹1,999 + 18% GST ₹360  = ₹2,359 total
  Prof     base ₹9,999 + 18% GST ₹1,800 = ₹11,799 total
"""
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
            'starter': {'name': "Starter's Plan", 'full_price': 1999},
            'professional': {'name': "Professional's Plan", 'full_price': 9999},
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
        """Paid agent upgrading: base ₹9,999 + 18% GST = ₹11,799 → 1179900 paise."""
        resp, amount = self._upgrade()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(amount, 1179900)

    def test_trial_agent_still_gets_the_trial_discount(self):
        """Trial agent with 20% discount: base ₹7,999 + GST = ₹9,439 → 943900 paise."""
        self.agent.plan_type = 'free_trial'
        self.agent.trial_ends_at = timezone.now() + timedelta(days=10)
        self.agent.save()
        resp, amount = self._upgrade()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(amount, 943900)

    def test_promo_code_no_longer_crashes_and_applies(self):
        """10% promo on ₹9,999 base = ₹8,999 base + GST ₹1,620 = ₹10,619 → 1061900 paise."""
        PromoCode.objects.create(code='UP10', discount_type='percentage', discount_value=10,
                                 is_active=True, applicable_plan='all')
        resp, amount = self._upgrade(promo_code='UP10')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.json().get('success', True), resp.json())
        self.assertEqual(amount, 1061900)

    def test_lower_or_same_plan_is_refused(self):
        self.agent.plan_type = 'professional'
        self.agent.save()
        resp, amount = self._upgrade(plan='starter')
        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(amount)
        resp, amount = self._upgrade(plan='professional')
        self.assertEqual(resp.status_code, 400)
        self.assertIsNone(amount)

    def test_trial_agent_can_buy_starter_plan(self):
        """Trial agents must be able to purchase the Starter (basic) plan."""
        self.agent.plan_type = 'free_trial'
        self.agent.trial_ends_at = timezone.now() + timedelta(days=10)
        self.agent.save()
        AgentSubscription.objects.filter(agent=self.agent).update(selected_plan="Trial Plan")
        resp, amount = self._upgrade(plan='starter')
        self.assertEqual(resp.status_code, 200, resp.content)
        # 20% off ₹1,999 = ₹1,599 base + GST ₹288 = ₹1,887 → 188700 paise
        self.assertEqual(amount, 188700)

    def test_event_challenge_agent_can_buy_starter_plan(self):
        """Event challenge (festive grant) agents can purchase the Starter plan."""
        from apps.event_referral.models import EventReferralCampaign, EventReferralParticipant

        campaign = EventReferralCampaign.objects.create(
            is_enabled=True, required_paid_referrals=3, window_hours=48,
        )
        EventReferralParticipant.objects.create(
            campaign=campaign, agent=self.agent,
            referral_code='TEST_EV_UPG', registered_at=timezone.now(),
            deadline_at=timezone.now() + timedelta(hours=48),
            window_hours=48, required_paid_referrals=3,
            status=EventReferralParticipant.STATUS_WON,
            grant_plan_slug="basic",
            grant_expires_at=timezone.now() + timedelta(days=16),
        )
        self.agent.plan_type = 'basic'
        self.agent.status = 'event_challenge'
        self.agent.save()
        AgentSubscription.objects.filter(agent=self.agent).delete()
        resp, amount = self._upgrade(plan='starter')
        self.assertEqual(resp.status_code, 200, resp.content)
        # No discount (not on free_trial), full base ₹1,999 + GST = ₹2,359 → 235900 paise
        self.assertEqual(amount, 235900)

    def test_starter_full_price_no_discount(self):
        """Starter plan at full price: base ₹1,999 + 18% GST = ₹2,359 → 235900 paise."""
        self.agent.plan_type = 'free_trial'
        self.agent.trial_ends_at = timezone.now() + timedelta(days=10)
        self.agent.upgrade_discount_percent = 0
        self.agent.save()
        SiteSetting.set_value('trial_upgrade_discount', 0, 'pricing')
        AgentSubscription.objects.filter(agent=self.agent).update(selected_plan="Trial Plan")
        resp, amount = self._upgrade(plan='starter')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(amount, 235900)
