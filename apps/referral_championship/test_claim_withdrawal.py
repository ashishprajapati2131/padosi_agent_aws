"""Audit CH3: a refund that drops the referral count below a slab must cancel any in-flight claim
for that slab (so admin doesn't still approve the voucher)."""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from apps.agents.models import Agent, AgentSubscription
from apps.referral_championship.models import (
    ChampionshipRewardClaim,
    ChampionshipRewardSlab,
)
from apps.referral_championship.services.attribution_service import (
    bind_referral_session,
    get_or_create_participant,
)
from apps.referral_championship.services.qualification_service import (
    process_championship_qualification,
    revert_championship_qualification,
)
from apps.referral_championship.testing import live_campaign


class ClaimWithdrawalOnRevertTests(TestCase):
    def setUp(self):
        self.campaign = live_campaign()
        self.slab = ChampionshipRewardSlab.objects.create(
            campaign=self.campaign,
            threshold=1,
            title="Fee Back",
            reward_type="membership_fee_back",
            value=Decimal("999"),
        )
        self.user1 = User.objects.create_user("a1@example.com", "a1@example.com", "x")
        self.user2 = User.objects.create_user("a2@example.com", "a2@example.com", "x")
        self.referrer = Agent.objects.create(
            user=self.user1,
            fullname="R",
            email="a1@example.com",
            mobile="9000000001",
            status="active",
        )
        self.referred = Agent.objects.create(
            user=self.user2,
            fullname="X",
            email="a2@example.com",
            mobile="9000000002",
            status="active",
        )
        self.part = get_or_create_participant(self.referrer, self.campaign)
        from apps.referral_championship.models import ChampionshipReferral

        ChampionshipReferral.objects.create(
            campaign=self.campaign,
            referrer=self.part,
            referred_agent=self.referred,
            registration_state="started",
        )

    def _qualify(self):
        sub = AgentSubscription.objects.create(
            agent=self.referred,
            selected_plan="Starter's Plan",
            payment_status="completed",
            status="active",
            registration_amount=Decimal("999"),
        )
        process_championship_qualification(self.referred, sub)

    def _claim(self, status):
        # evaluate_participant_rewards may already have created a locked claim.
        claim, _ = ChampionshipRewardClaim.objects.get_or_create(
            participant=self.part, reward_slab=self.slab, defaults={"status": status}
        )
        if claim.status != status:
            claim.status = status
            claim.save(update_fields=["status"])
        return claim

    def test_unlocked_claim_is_cancelled_on_refund(self):
        self._qualify()
        claim = self._claim("unlocked")
        revert_championship_qualification(self.referred, reason="refund")
        claim.refresh_from_db()
        self.assertEqual(claim.status, "cancelled")

    def test_dispatched_claim_is_left_alone(self):
        self._qualify()
        claim = self._claim("dispatched")
        revert_championship_qualification(self.referred, reason="refund")
        claim.refresh_from_db()
        self.assertEqual(claim.status, "dispatched")
