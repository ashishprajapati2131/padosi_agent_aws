"""Audit phase 4: CH8 landing tracking, CH16 slab counts, CH17 refresh debounce."""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from apps.agents.models import Agent
from apps.referral_championship.models import (
    ChampionshipGoogleReviewLog,
    ChampionshipLeaderboardCache,
    ChampionshipParticipant,
    ChampionshipReferral,
    ChampionshipRewardSlab,
)
from apps.referral_championship.services.attribution_service import (
    get_or_create_participant,
)
from apps.referral_championship.services.leaderboard_service import get_leaderboard_data
from apps.referral_championship.services.qualification_service import (
    _schedule_leaderboard_refresh,
)
from apps.referral_championship.services.reward_engine import slab_achieved_counts
from apps.referral_championship.testing import live_campaign


def _agent(n):
    user = User.objects.create_user(
        username=f"p4_{n}@example.com", email=f"p4_{n}@example.com", password="x"
    )
    return Agent.objects.create(
        user=user,
        fullname=f"Phase Four{n}",
        email=f"p4_{n}@example.com",
        mobile=f"90000050{n:02d}",
        status="active",
    )


class LandingTrackingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.campaign = live_campaign()
        self.participant = get_or_create_participant(_agent(1), self.campaign)

    def test_unknown_ref_redirects_to_general_landing_without_writes(self):
        resp = Client().get(
            reverse("championship:public_landing", kwargs={"ref_id": "PA-NOSUCH"})
        )
        self.assertRedirects(
            resp, reverse("championship:public_root"), fetch_redirect_response=False
        )
        self.assertFalse(ChampionshipReferral.objects.exists())
        self.assertFalse(ChampionshipGoogleReviewLog.objects.exists())

    def test_general_landing_writes_nothing_and_enrolls_nobody(self):
        _agent(2)
        before = ChampionshipParticipant.objects.count()
        self.assertEqual(
            Client().get(reverse("championship:public_root")).status_code, 200
        )
        self.assertEqual(ChampionshipParticipant.objects.count(), before)
        self.assertFalse(ChampionshipReferral.objects.exists())
        self.assertFalse(ChampionshipGoogleReviewLog.objects.exists())

    def test_general_landing_without_participants_does_not_enroll_first_agent(self):
        ChampionshipParticipant.objects.all().delete()
        resp = Client().get(reverse("championship:public_root"))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ChampionshipParticipant.objects.exists())

    def test_valid_ref_tracks_once_per_session(self):
        client = Client()
        url = reverse(
            "championship:public_landing",
            kwargs={"ref_id": self.participant.referral_id},
        )
        self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(
            ChampionshipReferral.objects.filter(referrer=self.participant).count(), 1
        )
        self.assertEqual(ChampionshipGoogleReviewLog.objects.count(), 1)
        self.assertEqual(
            client.session["championship_ref_id"], self.participant.referral_id
        )


class SlabCountTests(TestCase):
    def test_one_query_matches_per_slab_counts(self):
        campaign = live_campaign()
        for n, count in ((1, 0), (2, 5), (3, 12)):
            p = get_or_create_participant(_agent(n), campaign)
            ChampionshipParticipant.objects.filter(pk=p.pk).update(
                qualifying_referrals_count=count
            )
        slabs = list(
            ChampionshipRewardSlab.objects.filter(campaign=campaign, is_active=True)
        )
        with self.assertNumQueries(1 if slabs else 0):
            got = slab_achieved_counts(campaign, slabs)
        for s in slabs:
            self.assertEqual(
                got[s.id],
                ChampionshipParticipant.objects.filter(
                    campaign=campaign, qualifying_referrals_count__gte=s.threshold
                ).count(),
            )


class RefreshDebounceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.campaign = live_campaign()

    def test_second_refresh_in_window_is_skipped_then_applied_on_read(self):
        with self.captureOnCommitCallbacks(execute=False) as first:
            _schedule_leaderboard_refresh(self.campaign)
        with self.captureOnCommitCallbacks(execute=False) as second:
            _schedule_leaderboard_refresh(self.campaign)
        self.assertEqual((len(first), len(second)), (1, 0))

        p = get_or_create_participant(_agent(9), self.campaign)
        cache.delete(f"lb_refresh_{self.campaign.pk}")  # window over
        get_leaderboard_data(self.campaign)
        self.assertTrue(
            ChampionshipLeaderboardCache.objects.filter(
                campaign=self.campaign, participant=p
            ).exists()
        )
        self.assertIsNone(cache.get(f"lb_dirty_{self.campaign.pk}"))
