"""Audit 2026-10-01 F-17c: winning the Paldi challenge set the agent to
pending_approval on the basic plan even if they had meanwhile paid for
Professional or been approved."""
from django.test import TestCase

from apps.agents.models import Agent
from apps.event_referral.models import EventReferralCampaign, EventReferralParticipant
from apps.event_referral.services.participant_service import _grant_win


class GrantWinKeepsPaidPlanTests(TestCase):
    def setUp(self):
        EventReferralCampaign.objects.all().delete()
        self.campaign = EventReferralCampaign.objects.create(is_enabled=True, required_paid_referrals=2, window_hours=48)

    def _winner(self, status, plan_type):
        agent = Agent.objects.create(fullname='W', email=f'win.{status}.{plan_type or "none"}@example.com',
                                     mobile='9000000211', status=status, plan_type=plan_type)
        participant = EventReferralParticipant.create_for_agent(agent, self.campaign)
        _grant_win(participant)
        agent.refresh_from_db()
        return agent

    def test_paid_professional_agent_keeps_plan_and_approval(self):
        agent = self._winner('active', 'professional')
        self.assertEqual((agent.status, agent.plan_type), ('active', 'professional'))

    def test_challenger_still_gets_the_reward_plan(self):
        agent = self._winner('event_challenge', '')
        self.assertEqual((agent.status, agent.plan_type), ('pending_approval', 'basic'))
