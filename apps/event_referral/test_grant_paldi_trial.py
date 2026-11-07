from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.agents.models import Agent
from apps.event_referral.models import EventReferralCampaign, EventReferralParticipant
from apps.event_referral.services.participant_service import _grant_win

SEND = "apps.agents.services.brevo.email_service.send_generic"


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
        with patch(SEND, return_value=True) as send:
            call_command("grant_paldi_trial", until=self.until, stdout=StringIO())
        p.refresh_from_db()
        self.assertEqual(p.grant_plan_slug, "")
        send.assert_not_called()

    def test_failed_email_does_not_stop_the_grant(self):
        p = self._participant(1)
        out = StringIO()
        with patch(SEND, side_effect=RuntimeError("brevo down")):
            call_command(
                "grant_paldi_trial",
                until=self.until,
                apply=True,
                stdout=out,
                stderr=StringIO(),
            )
        p.refresh_from_db()
        self.assertEqual(p.grant_plan_slug, "basic")
        self.assertIn("Emails sent: 0, failed: 1.", out.getvalue())

    def test_unpaid_gets_basic_until_end_of_day_and_won_is_skipped(self):
        p = self._participant(1)
        winner = self._participant(2)
        _grant_win(winner)
        with patch(SEND, return_value=True) as send:
            call_command(
                "grant_paldi_trial", until=self.until, apply=True, stdout=StringIO()
            )
            # Second run: already granted, so no second email.
            call_command(
                "grant_paldi_trial", until=self.until, apply=True, stdout=StringIO()
            )
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], "t1@example.com")
        self.assertIn("free till", send.call_args.args[3])
        p.refresh_from_db()
        winner.refresh_from_db()
        p.agent.refresh_from_db()
        self.assertEqual(p.grant_plan_slug, "basic")
        self.assertEqual(
            p.grant_expires_at.strftime("%Y-%m-%d %H:%M"), f"{self.until} 23:59"
        )
        self.assertEqual(p.agent.plan_type, "basic")
        self.assertEqual(winner.grant_plan_slug, "")
