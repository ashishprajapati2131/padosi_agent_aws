"""The championship dashboard JSON (app and live refresh) crashed with
AttributeError 'voucher_code' as soon as the agent had a reward claim."""
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from apps.agents.models import Agent
from apps.referral_championship.models import (
    ChampionshipCampaign, ChampionshipParticipant, ChampionshipRewardClaim, ChampionshipRewardSlab,
)


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class DashboardWithClaimsTests(TestCase):
    def test_dashboard_json_loads_with_a_claim(self):
        user = User.objects.create_user('claimer@example.com', 'claimer@example.com', 'pw')
        agent = Agent.objects.create(fullname='Claimer', email='claimer@example.com', mobile='9000001301',
                                     status='active', plan_type='starter', user=user)
        campaign = ChampionshipCampaign.get_current()
        participant = ChampionshipParticipant.get_or_create_for_agent(agent, campaign)
        slab, _ = ChampionshipRewardSlab.objects.get_or_create(
            campaign=campaign, threshold=5,
            defaults={'reward_type': 'membership_fee_back', 'title': 'Fee Back', 'value': 1999, 'is_active': True})
        claim = ChampionshipRewardClaim.objects.create(participant=participant, reward_slab=slab, status='unlocked',
                                                       claim_data={'voucher_code': 'AMZ-123'})
        self.assertEqual(claim.voucher_code, 'AMZ-123')
        client = Client()
        client.force_login(user)
        resp = client.get('/agent/championship/agent/dashboard/', {'format': 'json'})
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertTrue(resp.json().get('success'), resp.content[:300])
        self.assertIn('AMZ-123', resp.content.decode())
