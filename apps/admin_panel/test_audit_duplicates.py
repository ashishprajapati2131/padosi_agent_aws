from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.agents.models import Agent, AgentReview
from apps.referral_championship.models import ChampionshipReferral
from apps.referral_championship.services.attribution_service import (
    get_or_create_participant,
)
from apps.referral_championship.testing import live_campaign


class AuditDuplicatesTests(TestCase):
    """Read-only report. Referrals and invoices now have unique rules (CH4, PAY13), so only
    reviews can still hold duplicates."""

    def test_reports_review_duplicates_and_zero_for_guarded_tables(self):
        agent = Agent.objects.create(
            fullname="D", email="d@example.com", mobile="9000000811", status="active"
        )
        other = Agent.objects.create(
            fullname="E", email="e@example.com", mobile="9000000812", status="active"
        )
        for _ in range(2):
            AgentReview.objects.create(agent=agent, reviewer_mobile="9111111111")
        AgentReview.objects.create(
            agent=agent, reviewer_mobile=""
        )  # blank mobiles are ignored
        AgentReview.objects.create(agent=agent, reviewer_mobile="")
        campaign = live_campaign()
        part = get_or_create_participant(agent, campaign)
        ChampionshipReferral.objects.create(
            campaign=campaign, referrer=part, referred_agent=other
        )
        # Rows with no referred agent (no signup yet) never count as duplicates.
        ChampionshipReferral.objects.create(campaign=campaign, referrer=part)
        ChampionshipReferral.objects.create(campaign=campaign, referrer=part)

        before = (AgentReview.objects.count(), ChampionshipReferral.objects.count())
        out = StringIO()
        call_command("audit_duplicates", stdout=out)
        text = out.getvalue()

        self.assertIn(
            f"agent_id={agent.pk}, reviewer_mobile=9111111111 (rows: 2)", text
        )
        self.assertIn("AgentReview (agent_id, reviewer_mobile): 1 duplicate keys", text)
        self.assertIn(
            "ChampionshipReferral (campaign_id, referred_agent_id): 0 duplicate keys",
            text,
        )
        self.assertIn("Invoice razorpay_payment_id: 0 duplicate keys", text)
        self.assertEqual(
            before, (AgentReview.objects.count(), ChampionshipReferral.objects.count())
        )
