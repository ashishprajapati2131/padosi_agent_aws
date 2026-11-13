from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.agents.models import Agent, AgentReview, Invoice
from apps.referral_championship.models import ChampionshipReferral
from apps.referral_championship.services.attribution_service import get_or_create_participant
from apps.referral_championship.testing import live_campaign


class AuditDuplicatesTests(TestCase):
    def test_reports_each_duplicate(self):
        agent = Agent.objects.create(
            fullname="D", email="d@example.com", mobile="9000000811", status="active"
        )
        other = Agent.objects.create(
            fullname="E", email="e@example.com", mobile="9000000812", status="active"
        )
        for _ in range(2):
            AgentReview.objects.create(agent=agent, reviewer_mobile="9111111111")
        AgentReview.objects.create(agent=agent, reviewer_mobile="")
        AgentReview.objects.create(agent=agent, reviewer_mobile="")
        campaign = live_campaign()
        part = get_or_create_participant(agent, campaign)
        for _ in range(2):
            ChampionshipReferral.objects.create(
                campaign=campaign, referrer=part, referred_agent=other
            )
        for i in range(2):
            Invoice.objects.create(
                invoice_number=f"PA/AUD/{i}", agent=agent, agent_name="D",
                agent_email="d@example.com", plan_name="P", plan_type="manual",
                base_amount="1", gst_amount="0", total_amount="1",
                discount_folder="x", razorpay_payment_id="pay_AUDITDUP",
            )
        before = (AgentReview.objects.count(), Invoice.objects.count())
        out = StringIO()
        call_command("audit_duplicates", stdout=out)
        text = out.getvalue()
        self.assertIn(f"agent_id={agent.pk}, reviewer_mobile=9111111111 (rows: 2)", text)
        self.assertIn("AgentReview (agent_id, reviewer_mobile): 1 duplicate keys", text)
        self.assertIn(f"campaign_id={campaign.pk}, referred_agent_id={other.pk} (rows: 2)", text)
        self.assertIn("razorpay_payment_id=pay_AUDITDUP (rows: 2)", text)
        self.assertEqual(before, (AgentReview.objects.count(), Invoice.objects.count()))
