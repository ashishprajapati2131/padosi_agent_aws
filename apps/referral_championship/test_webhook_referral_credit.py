"""Audit 2026-10-01 F-05: a payment activated by the Razorpay webhook (payer
closed the browser) must credit championship (PA-) and Paldi (EV-) referrers."""
from unittest.mock import patch

from apps.agents.models import Agent, AgentSubscription
from apps.agents.signup_test_support import ORDER_A, _SignupBase, _captured_webhook, _rzp
from apps.event_referral.models import EventReferral, EventReferralCampaign, EventReferralParticipant
from apps.referral_championship.models import ChampionshipCampaign, ChampionshipParticipant


class WebhookReferralCreditTests(_SignupBase):
    """Fix 1."""

    def _signup_with_code_and_webhook(self, email, code):
        session = self.client.session
        session['ref_code'] = code
        session.save()
        agent = self._signup(email, [ORDER_A])
        self.assertEqual(agent.referred_by_code, code)
        paise = self._paise(AgentSubscription.objects.get(razorpay_order_id=ORDER_A))
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(paise)), \
             patch('apps.agents.views.registration.razorpay_webhook_secret', return_value='whsec'):
            r = self.client.post('/razorpay-webhook/', data=_captured_webhook(ORDER_A, paise),
                                 content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE='sig')
        self.assertEqual(r.status_code, 200, r.content)
        return agent

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_webhook_credits_championship_referrer(self, _q):
        referrer = Agent.objects.create(fullname='Ref', email='pa.ref@example.com', mobile='9000000011',
                                        status='active', plan_type='professional')
        participant = ChampionshipParticipant.get_or_create_for_agent(referrer, ChampionshipCampaign.get_current())
        self._signup_with_code_and_webhook('pa.referred@example.com', participant.referral_id)
        participant.refresh_from_db()
        self.assertEqual(participant.qualifying_referrals_count, 1)

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_webhook_credits_event_referrer(self, _q):
        EventReferralCampaign.objects.all().delete()
        campaign = EventReferralCampaign.objects.create(is_enabled=True, required_paid_referrals=5, window_hours=48)
        referrer = Agent.objects.create(fullname='Ev', email='ev.ref@example.com', mobile='9000000012',
                                        status='event_challenge')
        participant = EventReferralParticipant.create_for_agent(referrer, campaign)
        agent = self._signup_with_code_and_webhook('ev.referred@example.com', participant.referral_code)
        row = EventReferral.objects.get(participant=participant, referred_agent=agent)
        self.assertEqual((row.state, row.counts), (EventReferral.STATE_PAID, True))
        participant.refresh_from_db()
        self.assertEqual(participant.paid_count, 1)
