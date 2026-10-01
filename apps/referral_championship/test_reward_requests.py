"""Every unlocked Championship Road reward can be requested; the request
reaches Admin > Championship > Reward Claims, the agent is told the team
will contact them within 24 hours, and the admin moves it along."""
import json
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.agents.models import Agent
from apps.referral_championship.models import (
    ChampionshipCampaign, ChampionshipParticipant, ChampionshipRewardClaim, ChampionshipRewardSlab,
)
from apps.referral_championship.views import admin_views


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class RewardRequestTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('roadagent', 'road.agent@example.com', 'pass')
        self.agent = Agent.objects.create(user=self.user, fullname='Road Agent', email='road.agent@example.com',
                                          mobile='9000001701', status='active', plan_type='professional')
        self.campaign = ChampionshipCampaign.get_current()
        self.participant = ChampionshipParticipant.get_or_create_for_agent(self.agent, self.campaign)
        self.participant.qualifying_referrals_count = 100
        self.participant.save()
        self.slabs = {}
        for threshold, rtype, title in ((5, 'membership_fee_back', 'Fee Back'), (50, 'gold', '1g Gold Coin'),
                                        (100, 'domestic_trip', 'Domestic Trip'), (200, 'international_trip', 'Intl Trip')):
            self.slabs[threshold], _ = ChampionshipRewardSlab.objects.get_or_create(
                campaign=self.campaign, threshold=threshold,
                defaults={'reward_type': rtype, 'title': title, 'value': 1000, 'is_active': True})
        self.client.force_login(self.user)

    def _request(self, threshold, **body):
        url = reverse('championship:agent_claim_reward', kwargs={'slab_id': self.slabs[threshold].pk})
        return self.client.post(url, data=json.dumps(body), content_type='application/json')

    def test_agent_at_100_can_request_the_100_reward(self):
        resp = self._request(100, note='Call me after 6 pm')
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertIn('24 hours', data['message'])
        claim = ChampionshipRewardClaim.objects.get(participant=self.participant, reward_slab=self.slabs[100])
        self.assertEqual(claim.status, 'processing')
        self.assertEqual(claim.claim_data['note'], 'Call me after 6 pm')
        self.assertEqual(claim.claim_data['agent_mobile'], '9000001701')
        self.assertEqual(claim.claim_data['referrals_at_claim'], 100)
        self.assertNotIn('voucher_provider', claim.claim_data)       # not a voucher reward

    def test_voucher_reward_keeps_the_provider_choice(self):
        self._request(5, voucher_provider='flipkart')
        claim = ChampionshipRewardClaim.objects.get(participant=self.participant, reward_slab=self.slabs[5])
        self.assertEqual(claim.claim_data['voucher_provider'], 'flipkart')

    def test_reward_above_the_count_cannot_be_requested(self):
        self.assertEqual(self._request(200).status_code, 400)

    def test_road_shows_claim_then_the_request_status(self):
        html = self.client.get('/agent/championship/agent/dashboard/').content.decode()
        claim_url = reverse('championship:agent_claim_reward', kwargs={'slab_id': 0})
        self.assertIn(claim_url, html)                              # JS posts to the real URL
        self.assertNotIn("'/championship/agent/claim/", html)
        self.assertIn(f"claimRewardModal('{self.slabs[100].pk}'", html)
        self.assertIn(f"claimRewardModal('{self.slabs[50].pk}'", html)
        self._request(100)
        html = self.client.get('/agent/championship/agent/dashboard/').content.decode()
        self.assertNotIn(f"claimRewardModal('{self.slabs[100].pk}'", html)
        self.assertIn('Requested', html)
        self.assertIn('claimDoneModal', html)

    def _admin(self, view, *args, method='post', **data):
        rf = RequestFactory()
        request = rf.post('/admin/championship/claims/', data) if method == 'post' else rf.get('/admin/championship/claims/', data)
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch('apps.referral_championship.views.admin_views._get_admin_from_session', return_value=1), \
             patch('apps.admin_panel.context_processors.admin_badge_counts', return_value={}):
            return view(request, *args)

    def test_admin_sees_and_manages_the_request(self):
        self._request(50, note='Ship to Ahmedabad office')
        claim = ChampionshipRewardClaim.objects.get(reward_slab=self.slabs[50])
        html = self._admin(admin_views.admin_reward_claims, method='get').content.decode()
        self.assertIn('Road Agent', html)
        self.assertIn('1g Gold Coin', html)
        self.assertIn('Ship to Ahmedabad office', html)
        self.assertIn('9000001701', html)

        resp = self._admin(admin_views.admin_update_reward_claim, claim.id, status='approved', voucher_code='GOLD-1',
                           next='https://evil.example.com/')
        self.assertEqual(resp['Location'], '/admin/championship/claims/')   # no open redirect
        claim.refresh_from_db()
        self.assertEqual((claim.status, claim.voucher_code), ('approved', 'GOLD-1'))

        self._admin(admin_views.admin_update_reward_claim, claim.id, status='dispatched',
                    courier_name='BlueDart', tracking_number='BD123')
        claim.refresh_from_db()
        self.assertEqual((claim.status, claim.courier_name, claim.tracking_number), ('dispatched', 'BlueDart', 'BD123'))
        self.assertIsNotNone(claim.dispatch_date)
        self.assertEqual([h['to'] for h in claim.claim_data['history']], ['approved', 'dispatched'])
        # The agent sees the new status and cannot re-request it.
        html = self.client.get('/agent/championship/agent/dashboard/').content.decode()
        self.assertIn('Dispatched', html)
        self.assertEqual(self._request(50).status_code, 409)

    def test_admin_rejects_unknown_status(self):
        self._request(5)
        claim = ChampionshipRewardClaim.objects.get(reward_slab=self.slabs[5])
        self._admin(admin_views.admin_update_reward_claim, claim.id, status='paid_out')
        claim.refresh_from_db()
        self.assertEqual(claim.status, 'processing')

    def test_app_can_request_a_physical_reward(self):
        from fastapi import HTTPException
        from fastapi_app.models.championship import ChampionshipRewardSlab as SASlab
        from fastapi_app.routers import championship as router
        slab = MagicMock(is_active=True, threshold=50, reward_type='gold', title='1g Gold Coin')
        participant = MagicMock(id=1, is_fraud_blocked=False, qualifying_referrals_count=60)
        claim = MagicMock(status='unlocked', claim_data={})
        db = MagicMock()

        def query(model):
            q = MagicMock()
            if model is SASlab:
                q.filter.return_value.first.return_value = slab
            else:
                q.filter.return_value.with_for_update.return_value.first.return_value = claim
            return q
        db.query.side_effect = query
        payload = MagicMock(slab_id=1, voucher_provider='amazon', shipping_address='Addr', note='Hi')
        with patch.object(router, 'get_current_campaign', return_value=MagicMock(id=1)), \
             patch.object(router, 'get_or_create_participant', return_value=participant):
            try:
                result = router.claim_milestone_reward(payload, current_agent=MagicMock(id=1, fullname='A', mobile='9', email='a@x'), db=db)
            except HTTPException as exc:  # pragma: no cover - shows the reason if it fails
                self.fail(f'API refused: {exc.status_code} {exc.detail}')
        self.assertIn('24 hours', result.message)
        self.assertEqual(claim.status, 'processing')
        self.assertNotIn('voucher_provider', claim.claim_data)
