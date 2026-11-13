"""CH15: grant_paldi_trial re-sends the trial email the first run failed to send."""
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.agents.models import Agent
from apps.event_referral.models import EventReferralCampaign, EventReferralParticipant

SEND = "apps.agents.services.brevo.email_service.send_generic"


class GrantPaldiTrialEmailRetryTests(TestCase):
    def setUp(self):
        EventReferralCampaign.objects.all().delete()
        self.campaign = EventReferralCampaign.objects.create(
            is_enabled=True, required_paid_referrals=2, window_hours=48
        )
        self.until = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")
        agent = Agent.objects.create(
            fullname="T", email="t5@example.com", mobile="9000000501",
            status="event_challenge", plan_type="",
        )
        self.p = EventReferralParticipant.create_for_agent(agent, self.campaign)

    def run_cmd(self, **kw):
        call_command("grant_paldi_trial", until=self.until, stdout=StringIO(),
                     stderr=StringIO(), **kw)

    def test_failed_email_is_sent_on_rerun_once(self):
        with patch(SEND, side_effect=RuntimeError("down")):
            self.run_cmd(apply=True)
        self.p.refresh_from_db()
        self.assertEqual(self.p.status, EventReferralParticipant.STATUS_WON)
        self.assertIsNone(self.p.win_emailed_at)
        with patch(SEND, return_value=True) as send:
            self.run_cmd()  # dry run: no send, no write
            send.assert_not_called()
            self.p.refresh_from_db()
            self.assertIsNone(self.p.win_emailed_at)
            self.run_cmd(apply=True)
            self.run_cmd(apply=True)  # already emailed: nothing more
        send.assert_called_once()
        self.p.refresh_from_db()
        self.assertIsNotNone(self.p.win_emailed_at)

    def test_email_granted_skips_emailed_unless_force(self):
        with patch(SEND, return_value=True) as send:
            self.run_cmd(apply=True)
            self.run_cmd(apply=True, email_granted=True)
            self.assertEqual(send.call_count, 1)
            self.run_cmd(apply=True, email_granted=True, force=True)
            self.assertEqual(send.call_count, 2)
