"""Audit 2026-10-01 F-25: the admin plan change rewrote selected_plan on every
subscription row of the agent (all past payments), mapped Exclusive and "No
Plan" to 'standard' (Starter features), created rows without dates and was
not logged."""
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.admin_panel.models import AdminActivityLog
from apps.agents.models import Agent, AgentSubscription


class AdminUpdatePlanTests(TestCase):
    def setUp(self):
        self.agent = Agent.objects.create(fullname='P', email='plan@example.com', mobile='9000000121',
                                          status='active', plan_type='starter')
        self.old = AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Starter's Plan", registration_amount='2359.00',
            payment_status='completed', status='inactive', razorpay_order_id='order_OLDPLAN000001')
        self.current = AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Starter's Plan", registration_amount='2359.00',
            payment_status='completed', status='active', razorpay_order_id='order_CURPLAN000001')

    def _update(self, plan, agent=None):
        from apps.admin_panel.views.agents import update_plan
        request = RequestFactory().post('/admin/agents/update-plan/', {'id': (agent or self.agent).pk, 'selected_plan': plan})
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch('apps.admin_panel.views.agents._get_admin_from_session', return_value=3), \
             patch('apps.admin_panel.views.dashboard._get_admin_from_session', return_value=3):
            return update_plan(request)

    def test_only_the_current_subscription_changes(self):
        self._update("Professional's Plan")
        self.old.refresh_from_db()
        self.current.refresh_from_db()
        self.agent.refresh_from_db()
        self.assertEqual(self.old.selected_plan, "Starter's Plan")          # history kept
        self.assertEqual(self.current.selected_plan, "Professional's Plan")
        self.assertEqual(self.agent.plan_type, 'professional')
        log = AdminActivityLog.objects.latest('id')
        self.assertEqual((log.admin_id, log.model_id), (3, self.agent.pk))

    def test_exclusive_and_no_plan_map_correctly(self):
        self._update('Exclusive Plan')
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.plan_type, 'exclusive')
        self._update('')
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.plan_type, '')

    def test_starter_mapping_unchanged(self):
        self._update("Starter's Plan")
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.plan_type, 'basic')

    def test_new_row_gets_dates(self):
        bare = Agent.objects.create(fullname='B', email='bare@example.com', mobile='9000000122', status='active')
        self._update("Professional's Plan", agent=bare)
        sub = AgentSubscription.objects.get(agent=bare)
        self.assertEqual((sub.payment_status, sub.status), ('completed', 'active'))
        self.assertEqual((sub.expires_at - sub.starts_at).days, 365)
