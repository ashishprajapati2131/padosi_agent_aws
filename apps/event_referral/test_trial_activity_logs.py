from datetime import datetime, timedelta
from django.test import TestCase, RequestFactory
from django.utils import timezone

from apps.agents.models import Agent, AgentProfile, AgentSubscription
from apps.event_referral.models import (
    EventReferralCampaign,
    EventReferralParticipant,
    TrialAgentActivityLog,
)
from apps.event_referral.views.admin_views import admin_trial_activity_logs
from apps.admin_panel.models.admin_auth import Admin


class TrialActivityLogsTest(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        EventReferralCampaign.objects.all().delete()
        self.campaign = EventReferralCampaign.objects.create(
            is_enabled=True, required_paid_referrals=2, window_hours=48
        )
        self.trial_agent = Agent.objects.create(
            fullname="Kumud Trial",
            email="kumud@example.com",
            mobile="9876543210",
            status="event_challenge",
            plan_type="basic",
        )
        self.participant = EventReferralParticipant.objects.create(
            campaign=self.campaign,
            agent=self.trial_agent,
            referral_code="EV-KUMUD1",
            registered_at=timezone.now(),
            deadline_at=timezone.now() + timedelta(days=2),
            window_hours=48,
            required_paid_referrals=2,
            grant_plan_slug="basic",
            grant_expires_at=timezone.now() + timedelta(days=16),
        )

        self.normal_agent = Agent.objects.create(
            fullname="Normal Agent",
            email="normal@example.com",
            mobile="9876543211",
            status="active",
            plan_type="professional",
        )

    def _auth_admin_request(self, req):
        req.COOKIES["session_token"] = "dummy_token"
        req._admin_session_cache = ("dummy_token", 1)
        return req

    def test_is_trial_agent_detection(self):
        self.assertTrue(TrialAgentActivityLog.is_trial_agent(self.trial_agent))
        self.assertFalse(TrialAgentActivityLog.is_trial_agent(self.normal_agent))

    def test_log_records_for_trial_agent(self):
        log = TrialAgentActivityLog.log(
            agent=self.trial_agent,
            activity_type=TrialAgentActivityLog.ACTIVITY_LOGIN,
            title="Agent Logged In",
            description="Logged in from test",
            details={"email": self.trial_agent.email},
        )
        self.assertIsNotNone(log)
        self.assertEqual(log.activity_type, "login")
        self.assertEqual(log.agent, self.trial_agent)
        self.assertEqual(log.participant, self.participant)
        self.assertEqual(TrialAgentActivityLog.objects.filter(agent=self.trial_agent).count(), 1)

    def test_log_ignores_non_trial_agent_without_force(self):
        log = TrialAgentActivityLog.log(
            agent=self.normal_agent,
            activity_type=TrialAgentActivityLog.ACTIVITY_LOGIN,
            title="Agent Logged In",
        )
        self.assertIsNone(log)
        self.assertEqual(TrialAgentActivityLog.objects.filter(agent=self.normal_agent).count(), 0)

    def test_log_with_force_records_for_any_agent(self):
        log = TrialAgentActivityLog.log(
            agent=self.normal_agent,
            activity_type=TrialAgentActivityLog.ACTIVITY_UPGRADE_SUCCESS,
            title="Plan Upgraded",
            force=True,
        )
        self.assertIsNotNone(log)
        self.assertEqual(log.activity_type, "upgrade_success")

    def test_admin_trial_activity_logs_view(self):
        TrialAgentActivityLog.log(
            agent=self.trial_agent,
            activity_type=TrialAgentActivityLog.ACTIVITY_LOGIN,
            title="Agent Logged In",
        )
        TrialAgentActivityLog.log(
            agent=self.trial_agent,
            activity_type=TrialAgentActivityLog.ACTIVITY_PROFILE_EDIT,
            title="Profile Edited (Basic Info)",
            details={"changed_fields": ["fullname", "agency_name"]},
        )
        TrialAgentActivityLog.log(
            agent=self.trial_agent,
            activity_type=TrialAgentActivityLog.ACTIVITY_UPGRADE_INITIATED,
            title="Upgrade Initiated (Starter)",
            details={"plan_type": "starter", "total_amount": 2359},
        )

        request = self.rf.get("/admin/event-referral/activity/")
        self._auth_admin_request(request)

        response = admin_trial_activity_logs(request)
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("Trial Agent Activity Tracking", content)
        self.assertIn("Kumud Trial", content)
        self.assertIn("Profile Edited", content)

    def test_admin_trial_activity_logs_csv_export(self):
        TrialAgentActivityLog.log(
            agent=self.trial_agent,
            activity_type=TrialAgentActivityLog.ACTIVITY_LOGIN,
            title="Agent Logged In",
        )

        request = self.rf.get("/admin/event-referral/activity/?export=csv")
        self._auth_admin_request(request)

        response = admin_trial_activity_logs(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Kumud Trial", response.content.decode("utf-8"))

