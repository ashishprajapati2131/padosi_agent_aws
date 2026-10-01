"""Audit 2026-10-01 F-33: stored datetimes are naive IST (USE_TZ=False), but the
admin renewal tracker compared them with UTC_TIMESTAMP() and the API with
datetime.utcnow(), so expiries and trials were off by 5h30m."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from django.test import SimpleTestCase, TestCase

from apps.agents.models import Agent, AgentSubscription


class RenewalStatsTests(TestCase):
    def test_renewal_buckets_use_local_time(self):
        from apps.admin_panel.views.dashboard import _fetch_renewal_stats
        agent = Agent.objects.create(fullname='R', email='renew@example.com', mobile='9000000161')
        now = datetime.now()
        for delta in (timedelta(hours=-3), timedelta(days=10), timedelta(days=45), timedelta(days=75)):
            AgentSubscription.objects.create(agent=agent, selected_plan="Starter's Plan", registration_amount=1,
                                             payment_status='completed', status='active', expires_at=now + delta)
        self.assertEqual(_fetch_renewal_stats(), {'expired': 1, 'next_30': 1, 'next_60': 1, 'next_90': 1})


class ApiTrialClockTests(SimpleTestCase):
    def test_trial_that_ended_two_hours_ago_is_over(self):
        from fastapi_app.services.dashboard_service import DashboardService
        service = DashboardService(MagicMock())
        service.setting_repo = MagicMock(get_json_value=MagicMock(return_value={}))
        agent = MagicMock(plan_type='free_trial', trial_ends_at=datetime.now() - timedelta(hours=2),
                          upgrade_discount_percent=0, referral_reward_type=None)
        info = service._build_trial_info(agent, None)
        self.assertFalse(info.is_on_trial)
        self.assertTrue(info.trial_expired)
