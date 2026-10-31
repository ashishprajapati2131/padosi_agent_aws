from django.contrib.auth.models import User
from django.test import TestCase

from apps.agents.models import Agent, AgentSubscription, City
from apps.referral_championship.models import ChampionshipLeaderboardCache
from apps.referral_championship.services.attribution_service import (
    get_or_create_participant,
)
from apps.referral_championship.services.leaderboard_service import (
    get_leaderboard_data,
    refresh_leaderboard_cache,
)
from apps.referral_championship.services.qualification_service import (
    process_championship_qualification,
)
from apps.referral_championship.testing import live_campaign


def _agent(n, **extra):
    user = User.objects.create_user(
        username=f"lb{n}@example.com", email=f"lb{n}@example.com", password="pass"
    )
    return Agent.objects.create(
        user=user,
        fullname=f"Agent Number{n}",
        email=f"lb{n}@example.com",
        mobile=f"98765432{n:02d}",
        status="active",
        **extra,
    )


class LeaderboardRefreshTests(TestCase):
    def setUp(self):
        self.campaign = live_campaign()
        self.referrer = _agent(1)
        self.candidate = _agent(2)

    def test_refresh_runs_after_commit_and_credit_is_kept(self):
        participant = get_or_create_participant(self.referrer, self.campaign)
        self.candidate.referred_by_code = participant.referral_id
        self.candidate.save()
        sub = AgentSubscription.objects.create(
            agent=self.candidate,
            selected_plan="Starter's Plan",
            payment_status="completed",
            status="active",
            registration_amount=999,
        )

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.assertTrue(process_championship_qualification(self.candidate, sub))
        participant.refresh_from_db()
        self.assertEqual(participant.qualifying_referrals_count, 1)
        self.assertEqual(len(callbacks), 1)

        callbacks[0]()
        row = ChampionshipLeaderboardCache.objects.get(
            campaign=self.campaign, participant=participant
        )
        self.assertEqual((row.rank, row.referral_count), (1, 1))

    def test_refresh_ranks_and_updates_existing_rows(self):
        p1 = get_or_create_participant(self.referrer, self.campaign)
        p2 = get_or_create_participant(self.candidate, self.campaign)
        p1.qualifying_referrals_count = 1
        p1.save()
        refresh_leaderboard_cache(self.campaign)

        p2.qualifying_referrals_count = 3
        p2.save()
        refresh_leaderboard_cache(self.campaign)

        ranks = dict(
            ChampionshipLeaderboardCache.objects.filter(
                campaign=self.campaign
            ).values_list("participant_id", "rank")
        )
        self.assertEqual(ranks[p2.id], 1)
        self.assertEqual(ranks[p1.id], 2)
        p2.refresh_from_db()
        self.assertEqual(p2.current_rank, 1)

    def test_leaderboard_city_lookup_does_not_query_per_row(self):
        ahmedabad = City.objects.create(name="ahmedabad")
        surat = City.objects.create(name="surat")
        self.referrer.serviceableCities.add(surat, ahmedabad)
        for n in range(3, 6):
            get_or_create_participant(_agent(n), self.campaign)
        get_or_create_participant(self.referrer, self.campaign)
        refresh_leaderboard_cache(self.campaign)

        with self.assertNumQueries(2):  # cache rows + one prefetch of cities
            rows = get_leaderboard_data(self.campaign)
        by_agent = {r["agent_id"]: r["city"] for r in rows}
        self.assertEqual(
            by_agent[self.referrer.id], "Ahmedabad"
        )  # lowest pk, same as .first()
