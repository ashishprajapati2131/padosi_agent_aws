"""Audit phase 3 quick fixes: CH12, CH14."""

from datetime import timedelta

from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.agents.models import Agent
from apps.event_referral.models import (
    EventReferralCampaign,
    EventReferralParticipant,
    TrialAgentActivityLog,
)
from apps.event_referral.services.participant_service import _grant_win
from apps.event_referral.views.admin_views import admin_trial_activity_logs


class Phase3QuickTests(TestCase):
    def setUp(self):
        EventReferralCampaign.objects.all().delete()
        self.campaign = EventReferralCampaign.objects.create(
            is_enabled=True, required_paid_referrals=2, window_hours=48
        )

    # CH12
    def test_grant_win_keeps_suspended_and_blacklisted_agents_blocked(self):
        for status in ("suspended", "blacklisted"):
            agent = Agent.objects.create(
                fullname="W",
                email=f"p3q.{status}@example.com",
                mobile="9000003201",
                status=status,
                plan_type="",
            )
            _grant_win(EventReferralParticipant.create_for_agent(agent, self.campaign))
            agent.refresh_from_db()
            self.assertEqual(agent.status, status)

    # CH14
    def test_activity_csv_neutralises_formulas(self):
        agent = Agent.objects.create(
            fullname='=HYPERLINK("http://x")',
            email="p3q.csv@example.com",
            mobile="9000003202",
            status="event_challenge",
            plan_type="basic",
        )
        EventReferralParticipant.objects.create(
            campaign=self.campaign,
            agent=agent,
            referral_code="EV-P3QCSV",
            registered_at=timezone.now(),
            deadline_at=timezone.now() + timedelta(days=2),
            window_hours=48,
            required_paid_referrals=2,
            grant_plan_slug="basic",
            grant_expires_at=timezone.now() + timedelta(days=16),
        )
        TrialAgentActivityLog.log(
            agent=agent,
            activity_type=TrialAgentActivityLog.ACTIVITY_LOGIN,
            title="@SUM(1)",
        )
        request = RequestFactory().get("/admin/event-referral/activity/?export=csv")
        request.COOKIES["session_token"] = "dummy_token"
        request._admin_session_cache = ("dummy_token", 1)
        body = admin_trial_activity_logs(request).content.decode("utf-8")
        self.assertIn("'=HYPERLINK", body)
        self.assertIn("'@SUM(1)", body)
        self.assertIn("9000003202", body)
