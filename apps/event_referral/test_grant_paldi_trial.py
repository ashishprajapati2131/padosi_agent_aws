from datetime import datetime, timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.agents.models import Agent
from apps.event_referral.models import EventReferralCampaign, EventReferralParticipant
from apps.event_referral.services.participant_service import _grant_win


class GrantPaldiTrialTests(TestCase):
    def setUp(self):
        EventReferralCampaign.objects.all().delete()
        self.campaign = EventReferralCampaign.objects.create(
            is_enabled=True, required_paid_referrals=2, window_hours=48
        )
        self.until = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")

    def _participant(self, n):
        agent = Agent.objects.create(
            fullname="T",
            email=f"t{n}@example.com",
            mobile=f"900000030{n}",
            status="event_challenge",
            plan_type="",
        )
        return EventReferralParticipant.create_for_agent(agent, self.campaign)

    def test_dry_run_changes_nothing(self):
        p = self._participant(1)
        call_command("grant_paldi_trial", until=self.until, stdout=StringIO())
        p.refresh_from_db()
        self.assertEqual(p.grant_plan_slug, "")

    def test_unpaid_gets_basic_until_end_of_day_and_won_is_skipped(self):
        p = self._participant(1)
        winner = self._participant(2)
        _grant_win(winner)
        call_command(
            "grant_paldi_trial", until=self.until, apply=True, stdout=StringIO()
        )
        p.refresh_from_db()
        winner.refresh_from_db()
        p.agent.refresh_from_db()
        self.assertEqual(p.grant_plan_slug, "basic")
        self.assertEqual(
            p.grant_expires_at.strftime("%Y-%m-%d %H:%M"), f"{self.until} 23:59"
        )
        self.assertEqual(p.agent.plan_type, "basic")
        self.assertEqual(winner.grant_plan_slug, "")
