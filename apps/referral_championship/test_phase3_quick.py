"""Audit phase 3 quick fixes: CH5, CH6, CH7, CH10, CH13."""

from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.agents.models import Agent
from apps.referral_championship.models import (
    ChampionshipCampaign,
    ChampionshipLeaderboardCache,
    ChampionshipParticipant,
    ChampionshipReferral,
    ChampionshipRewardClaim,
    ChampionshipRewardSlab,
)
from apps.referral_championship.services import qualification_service
from apps.referral_championship.services.attribution_service import (
    validate_referral_integrity,
)
from apps.referral_championship.services.leaderboard_service import (
    refresh_leaderboard_cache,
)
from apps.referral_championship.views import admin_views


class Phase3QuickTests(TestCase):
    def setUp(self):
        self.campaign = ChampionshipCampaign.get_current()
        self.agents = [
            Agent.objects.create(
                fullname=f"P{i}",
                email=f"p3q{i}@example.com",
                mobile=f"90000031{i:02d}",
                status="active",
            )
            for i in range(3)
        ]
        self.parts = [
            ChampionshipParticipant.get_or_create_for_agent(a, self.campaign)
            for a in self.agents
        ]

    # CH5
    def test_revert_locks_referrer_before_recount(self):
        referrer = self.parts[0]
        referrer.qualifying_referrals_count = 1
        referrer.save()
        ChampionshipReferral.objects.create(
            campaign=self.campaign,
            referrer=referrer,
            referred_agent=self.agents[1],
            referral_id=referrer.referral_id,
            is_qualifying=True,
            registration_state="paid",
        )
        real = ChampionshipParticipant.objects.select_for_update
        with patch.object(
            ChampionshipParticipant.objects, "select_for_update", side_effect=real
        ) as sfu:
            self.assertIs(
                qualification_service.revert_championship_qualification(self.agents[1]),
                True,
            )
        sfu.assert_called()
        referrer.refresh_from_db()
        self.assertEqual(referrer.qualifying_referrals_count, 0)

    # CH6
    def test_frozen_leaderboard_is_not_reranked(self):
        refresh_leaderboard_cache(self.campaign)
        ChampionshipLeaderboardCache.objects.filter(campaign=self.campaign).update(
            is_frozen=True
        )
        before = dict(
            ChampionshipLeaderboardCache.objects.values_list("participant_id", "rank")
        )
        p = self.parts[2]
        p.qualifying_referrals_count = 50
        p.save()
        refresh_leaderboard_cache(self.campaign)
        self.assertEqual(
            dict(
                ChampionshipLeaderboardCache.objects.values_list(
                    "participant_id", "rank"
                )
            ),
            before,
        )

    # CH7
    def test_fraud_blocked_participant_row_removed_on_refresh(self):
        refresh_leaderboard_cache(self.campaign)
        blocked = self.parts[1]
        blocked.is_fraud_blocked = True
        blocked.save()
        refresh_leaderboard_cache(self.campaign)
        ids = set(
            ChampionshipLeaderboardCache.objects.filter(
                campaign=self.campaign
            ).values_list("participant_id", flat=True)
        )
        self.assertNotIn(blocked.pk, ids)
        self.assertIn(self.parts[0].pk, ids)

    # CH10
    def test_self_referral_mobile_matches_with_country_code_or_zero(self):
        self.agents[1].mobile = "+91 9000003100"
        ok, _ = validate_referral_integrity(self.parts[0], self.agents[1])
        self.assertFalse(ok)
        self.agents[1].mobile = "09000003100"
        ok, _ = validate_referral_integrity(self.parts[0], self.agents[1])
        self.assertFalse(ok)
        self.agents[1].mobile = "9000003199"
        ok, _ = validate_referral_integrity(self.parts[0], self.agents[1])
        self.assertTrue(ok)

    # CH13
    def _update(self, claim, status):
        request = RequestFactory().post(
            "/admin/championship/claims/", {"status": status}
        )
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch(
            "apps.referral_championship.views.admin_views._get_admin_from_session",
            return_value=1,
        ):
            return admin_views.admin_update_reward_claim(request, claim.id)

    def test_delivered_claim_cannot_move_back(self):
        slab = ChampionshipRewardSlab.objects.create(
            campaign=self.campaign,
            threshold=5,
            title="Fee back",
            reward_type="membership_fee_back",
        )
        claim = ChampionshipRewardClaim.objects.create(
            participant=self.parts[0], reward_slab=slab, status="delivered"
        )
        self._update(claim, "processing")
        claim.refresh_from_db()
        self.assertEqual(claim.status, "delivered")
        self._update(claim, "redeemed")
        claim.refresh_from_db()
        self.assertEqual(claim.status, "redeemed")
        self._update(claim, "dispatched")
        claim.refresh_from_db()
        self.assertEqual(claim.status, "redeemed")
