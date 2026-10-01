"""Owner decision 2026-10-02: a Paldi (48-hour) challenger's paid referrals
also count in the Referral Championship: road, Live Slab Pulse, claims and
leaderboard, during and after the challenge."""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, TestCase, override_settings

from apps.agents.models import Agent
from apps.event_referral.models import EventReferral, EventReferralCampaign, EventReferralParticipant
from apps.event_referral.views import admin_views
from apps.referral_championship.models import (
    ChampionshipCampaign, ChampionshipParticipant, ChampionshipRewardClaim, ChampionshipRewardSlab,
)


@override_settings(DEBUG=True, ALLOWED_HOSTS=['testserver', 'localhost'])
class PaldiCountsInChampionshipTests(TestCase):
    def setUp(self):
        EventReferralCampaign.objects.all().delete()
        self.ev_campaign = EventReferralCampaign.objects.create(is_enabled=True, required_paid_referrals=5,
                                                                window_hours=48)
        self.champ = ChampionshipCampaign.get_current()
        for threshold, rtype, title in ((5, 'membership_fee_back', 'Fee Back'), (10, 'plan_upgrade', 'Pro Free')):
            ChampionshipRewardSlab.objects.get_or_create(
                campaign=self.champ, threshold=threshold,
                defaults={'reward_type': rtype, 'title': title, 'value': 1000, 'is_active': True})
        self.user = User.objects.create_user('challenger.c@example.com', 'challenger.c@example.com', 'pw')
        self.challenger = Agent.objects.create(fullname='Challenger', email='challenger.c@example.com',
                                               mobile='9000001201', status='event_challenge', plan_type='',
                                               user=self.user)
        self.participant = EventReferralParticipant.create_for_agent(self.challenger, self.ev_campaign)

    def _admin(self, view, **post):
        request = RequestFactory().post('/admin/event-referral/x/', post)
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch('apps.event_referral.views.admin_views._get_admin_from_session', return_value=1):
            view(request, self.participant.pk)

    def _champ_participant(self):
        return ChampionshipParticipant.objects.get(agent=self.challenger, campaign=self.champ)

    def test_ten_paid_referrals_move_the_road_and_unlock_claims(self):
        self._admin(admin_views.admin_test_add_referrals, count='10')
        cp = self._champ_participant()
        self.assertEqual(cp.qualifying_referrals_count, 10)
        unlocked = set(ChampionshipRewardClaim.objects.filter(participant=cp)
                       .values_list('reward_slab__threshold', flat=True))
        self.assertTrue({5, 10} <= unlocked, unlocked)

        # Paldi: the win happens once at 5; later referrals are still recorded as paid.
        self.participant.refresh_from_db()
        self.challenger.refresh_from_db()
        self.assertEqual(self.participant.status, EventReferralParticipant.STATUS_WON)
        self.assertEqual(self.participant.paid_count, 10)
        self.assertEqual(EventReferral.objects.filter(participant=self.participant,
                                                      state=EventReferral.STATE_PAID).count(), 10)
        self.assertEqual((self.challenger.status, self.challenger.plan_type), ('pending_approval', 'basic'))

    def test_dashboard_shows_the_progress(self):
        self._admin(admin_views.admin_test_add_referrals, count='10')
        client = Client()
        client.force_login(self.user)
        data = client.get('/agent/championship/agent/dashboard/', {'format': 'json'}).json()
        self.assertTrue(data.get('success', True), data)
        text = str(data)
        self.assertIn("'verified_referrals': 10", text)
        pulse = {row.get('threshold'): row.get('achieved_count') for row in data.get('slab_pulse_board') or
                 (data.get('data') or {}).get('slab_pulse_board') or []}
        self.assertEqual(pulse.get(5), 1, data)
        self.assertEqual(pulse.get(10), 1, data)

    def test_remove_test_referrals_takes_them_out_of_the_championship(self):
        self._admin(admin_views.admin_test_add_referrals, count='3')
        self.assertEqual(self._champ_participant().qualifying_referrals_count, 3)
        self._admin(admin_views.admin_test_remove_referrals)
        self.assertEqual(self._champ_participant().qualifying_referrals_count, 0)
