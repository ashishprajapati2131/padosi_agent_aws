"""Audit 2026-10-01 F-18: a championship reward claim cannot be re-submitted
after the team acted on it, and fraud-blocked participants cannot claim
(website and mobile API)."""
import json
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase

from apps.agents.models import Agent, AgentSubscription
from apps.referral_championship.models import (
    ChampionshipCampaign, ChampionshipParticipant, ChampionshipRewardClaim, ChampionshipRewardSlab,
)


def _paid_sub(agent, order='order_REFFIX00000001', pay='pay_REFFIX000000001'):
    return AgentSubscription.objects.create(
        agent=agent, selected_plan="Starter's Plan", registration_amount=100,
        payment_status='completed', status='active',
        razorpay_order_id=order, razorpay_payment_id=pay,
    )


class ChampionshipClaimGuardTests(TestCase):
    """Fix 5 (website and mobile API)."""

    def setUp(self):
        self.user = User.objects.create_user('claimer', 'claimer@example.com', 'pass')
        self.agent = Agent.objects.create(user=self.user, fullname='Claimer', email='claimer@example.com',
                                          mobile='9000000021', status='active', plan_type='professional')
        _paid_sub(self.agent, 'order_CLAIM000000001', 'pay_CLAIM0000000001')
        self.campaign = ChampionshipCampaign.get_current()
        self.participant = ChampionshipParticipant.get_or_create_for_agent(self.agent, self.campaign)
        self.participant.qualifying_referrals_count = 5
        self.participant.save()
        self.slab = ChampionshipRewardSlab.objects.create(
            campaign=self.campaign, threshold=5, title='Fee back', reward_type='membership_fee_back')
        self.client.force_login(self.user)

    def _claim(self, address='New address'):
        return self.client.post(self._url_ok(),
                                data=json.dumps({'voucher_provider': 'amazon', 'shipping_address': address}),
                                content_type='application/json')

    def _url_ok(self):
        from django.urls import reverse
        return reverse('championship:agent_claim_reward', kwargs={'slab_id': self.slab.pk})

    def test_first_claim_and_address_update_still_work(self):
        self.assertEqual(self._claim('Addr 1').status_code, 200)
        self.assertEqual(self._claim('Addr 2').status_code, 200)
        claim = ChampionshipRewardClaim.objects.get(participant=self.participant, reward_slab=self.slab)
        self.assertEqual((claim.status, claim.claim_data['shipping_address']), ('processing', 'Addr 2'))

    def test_dispatched_claim_cannot_be_resubmitted(self):
        claim = ChampionshipRewardClaim.objects.create(
            participant=self.participant, reward_slab=self.slab, status='dispatched',
            claim_data={'shipping_address': 'Original'})
        resp = self._claim('Second address')
        self.assertEqual(resp.status_code, 409, resp.content)
        claim.refresh_from_db()
        self.assertEqual((claim.status, claim.claim_data['shipping_address']), ('dispatched', 'Original'))

    def test_fraud_blocked_participant_cannot_claim(self):
        self.participant.is_fraud_blocked = True
        self.participant.save()
        self.assertEqual(self._claim().status_code, 403)
        self.assertFalse(ChampionshipRewardClaim.objects.filter(participant=self.participant).exists())

    def test_top_three_prize_cannot_be_claimed(self):
        # Every count-based reward is claimable (owner request 2026-10-02);
        # the Top 3 prize (900+) is decided by the final leaderboard.
        self.slab.threshold, self.slab.reward_type = 999, 'family_trip'
        self.slab.save()
        self.participant.qualifying_referrals_count = 1000
        self.participant.save()
        self.assertEqual(self._claim().status_code, 400)

    def test_physical_reward_can_now_be_claimed(self):
        self.slab.reward_type = 'gold'
        self.slab.save()
        self.assertEqual(self._claim().status_code, 200)

    def _api_claim(self, participant, slab, claim):
        from fastapi import HTTPException
        from fastapi_app.models.championship import ChampionshipRewardSlab as SASlab
        from fastapi_app.routers import championship as router
        db = MagicMock()

        def query(model):
            q = MagicMock()
            if model is SASlab:
                q.filter.return_value.first.return_value = slab
            else:
                q.filter.return_value.with_for_update.return_value.first.return_value = claim
            return q
        db.query.side_effect = query
        payload = MagicMock(slab_id=1, voucher_provider='amazon', shipping_address='x')
        with patch.object(router, 'get_current_campaign', return_value=MagicMock(id=1)), \
             patch.object(router, 'get_or_create_participant', return_value=participant):
            try:
                router.claim_milestone_reward(payload, current_agent=MagicMock(id=1), db=db)
                return 200, db
            except HTTPException as exc:
                return exc.status_code, db

    def test_api_dispatched_claim_cannot_be_resubmitted(self):
        slab = MagicMock(is_active=True, threshold=5, reward_type='membership_fee_back', title='Fee back')
        participant = MagicMock(id=1, is_fraud_blocked=False, qualifying_referrals_count=5)
        claim = MagicMock(status='dispatched')
        status, db = self._api_claim(participant, slab, claim)
        self.assertEqual(status, 409)
        self.assertEqual(claim.status, 'dispatched')
        db.commit.assert_not_called()

    def test_api_fraud_blocked_and_processing_update(self):
        slab = MagicMock(is_active=True, threshold=5, reward_type='membership_fee_back', title='Fee back')
        blocked = MagicMock(id=1, is_fraud_blocked=True, qualifying_referrals_count=5)
        self.assertEqual(self._api_claim(blocked, slab, None)[0], 403)
        ok = MagicMock(id=1, is_fraud_blocked=False, qualifying_referrals_count=5)
        claim = MagicMock(status='processing')
        status, db = self._api_claim(ok, slab, claim)
        self.assertEqual(status, 200)
        db.commit.assert_called_once()
