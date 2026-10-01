"""Audit 2026-10-01 F-09: subscription expiry, behind an admin switch that is
OFF by default (owner decision). OFF keeps today's behaviour exactly."""
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.agents.models import Agent, AgentDraft, AgentSubscription
from apps.agents.services.account_auth import agent_can_access_dashboard
from apps.agents.signup_test_support import PAY_A, _rzp
from apps.home.models import SiteSetting
from apps.home.services.agent_filters import listed_agents_queryset


def _agent(email, expires_delta, status='active'):
    user = User.objects.create_user(email, email, None)
    agent = Agent.objects.create(user=user, fullname='Exp', email=email, mobile='9000000221',
                                 status=status, plan_type='starter')
    AgentSubscription.objects.create(
        agent=agent, selected_plan="Starter's Plan", registration_amount='2359.00',
        payment_status='completed', status='active',
        starts_at=datetime.now() - timedelta(days=400),
        expires_at=(datetime.now() + expires_delta) if expires_delta is not None else None,
        razorpay_order_id=f'order_EXP{agent.pk:011d}', razorpay_payment_id=f'pay_EXP{agent.pk:012d}')
    return agent


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class SubscriptionExpiryTests(TestCase):
    def setUp(self):
        cache.clear()
        SiteSetting.set_value('pricing_config', {
            'starter': {'name': "Starter's Plan", 'full_price': 1999},
            'professional': {'name': "Professional's Plan", 'full_price': 4999},
        }, 'pricing')
        SiteSetting.set_value('trial_plan_config', {'price': 99, 'duration_days': 30}, 'pricing')
        self.expired = _agent('expired@example.com', timedelta(days=-5))
        self.valid = _agent('valid@example.com', timedelta(days=100))
        self.legacy = _agent('legacy@example.com', None)

    def _switch(self, on):
        SiteSetting.set_value('subscription_expiry_enforced', '1' if on else '0', 'security')

    def _listed_emails(self):
        return set(listed_agents_queryset().values_list('email', flat=True))

    def test_switch_off_changes_nothing(self):
        self._switch(False)
        self.assertTrue(agent_can_access_dashboard(self.expired))
        self.assertIn('expired@example.com', self._listed_emails())

    def test_switch_on_ends_access_and_listing_after_expiry(self):
        self._switch(True)
        self.assertFalse(agent_can_access_dashboard(self.expired))
        self.assertTrue(agent_can_access_dashboard(self.valid))
        self.assertTrue(agent_can_access_dashboard(self.legacy))   # no expiry date: never expires
        listed = self._listed_emails()
        self.assertNotIn('expired@example.com', listed)
        self.assertIn('valid@example.com', listed)
        self.assertIn('legacy@example.com', listed)

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_expired_agent_can_renew_from_chooseplan(self, _q):
        self._switch(True)
        self.assertFalse(AgentDraft.objects.filter(email=self.expired.email).exists())
        self.client.force_login(self.expired.user)
        self.assertEqual(self.client.get('/chooseplan/').status_code, 200)
        with patch('apps.agents.views.registration.create_checkout_order', return_value=('order_RENEWAL000001', False)):
            r = self.client.post('/agent-register/complete/', data={'plan_type': 'starter'},
                                 content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        renewal = AgentSubscription.objects.get(razorpay_order_id='order_RENEWAL000001')
        paise = int(round(float(renewal.registration_amount) * 100))
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(paise)):
            r = self.client.post('/agent-register/verify-payment/', data={
                'razorpay_order_id': 'order_RENEWAL000001', 'razorpay_payment_id': PAY_A,
                'razorpay_signature': 'sig'}, content_type='application/json')
        self.assertTrue(r.json()['success'], r.json())
        self.expired.refresh_from_db()
        renewal.refresh_from_db()
        self.assertEqual(self.expired.status, 'active')
        self.assertGreater(renewal.expires_at, datetime.now() + timedelta(days=360))
        self.assertTrue(agent_can_access_dashboard(self.expired))

    def test_command_marks_expired_only_when_switched_on(self):
        out = StringIO()
        call_command('expire_subscriptions', '--apply', stdout=out)
        self.assertIn('OFF', out.getvalue())
        self._switch(True)
        out = StringIO()
        call_command('expire_subscriptions', '--apply', stdout=out)
        self.assertIn('expired@example.com', out.getvalue())
        statuses = dict(AgentSubscription.objects.values_list('agent__email', 'status'))
        self.assertEqual(statuses['expired@example.com'], 'expired')
        self.assertEqual(statuses['valid@example.com'], 'active')

    def test_admin_switch_is_saved_from_security_settings(self):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory
        from apps.admin_panel.views.settings import update_settings
        from apps.agents.services.subscription_expiry import expiry_enforced
        request = RequestFactory().post('/admin/settings/update/', {
            'group': 'security', 'rate_limit_clicks': '10', 'rate_limit_timeframe': '2',
            'subscription_expiry_enforced': '1'})
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch('apps.admin_panel.views.settings._get_admin_from_session', return_value=1):
            update_settings(request)
        self.assertTrue(expiry_enforced())

    def test_security_settings_page_shows_the_switch(self):
        from django.test import RequestFactory
        from apps.admin_panel.views.settings import security
        request = RequestFactory().get('/admin/settings/security/')
        request.session = {}
        with patch('apps.admin_panel.views.settings._get_admin_from_session', return_value=1), \
             patch('apps.admin_panel.context_processors.admin_badge_counts', return_value={}):
            html = security(request).content.decode()
        self.assertIn('name="subscription_expiry_enforced"', html)
        self.assertIn('OFF (no expiry)', html)
