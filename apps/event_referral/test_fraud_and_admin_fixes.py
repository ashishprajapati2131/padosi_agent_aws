"""Audit 2026-10-01 F-17: fraud-rejected Paldi referrals must not count once
paid; admin Extend / Restore must work and must not re-grant a win."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.agents.models import Agent, AgentSubscription
from apps.event_referral.models import EventReferral, EventReferralCampaign, EventReferralParticipant
from apps.event_referral.services.qualification_service import qualify_event_referral, register_referred_agent


def _paid_sub(agent, order='order_REFFIX00000001', pay='pay_REFFIX000000001'):
    return AgentSubscription.objects.create(
        agent=agent, selected_plan="Starter's Plan", registration_amount=100,
        payment_status='completed', status='active',
        razorpay_order_id=order, razorpay_payment_id=pay,
    )


class EventReferralFixTests(TestCase):
    """Fixes 3 and 4."""

    def setUp(self):
        EventReferralCampaign.objects.all().delete()
        self.campaign = EventReferralCampaign.objects.create(is_enabled=True, required_paid_referrals=2, window_hours=48)
        self.referrer = Agent.objects.create(fullname='Referrer', email='referrer@example.com',
                                             mobile='9000000001', status='event_challenge', plan_type='')
        self.participant = EventReferralParticipant.create_for_agent(self.referrer, self.campaign)

    def test_fraud_rejected_referral_does_not_count_after_payment(self):
        same_mobile = Agent.objects.create(fullname='Puppet', email='puppet@example.com', mobile='9000000001',
                                           status='pending_approval', plan_type='starter',
                                           referred_by_code=self.participant.referral_code)
        register_referred_agent(same_mobile)
        qualify_event_referral(same_mobile, _paid_sub(same_mobile))
        row = EventReferral.objects.get(participant=self.participant, referred_agent=same_mobile)
        self.assertEqual((row.state, row.counts), (EventReferral.STATE_REJECTED, False))
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.paid_count, 0)

    def test_genuine_referral_still_counts(self):
        genuine = Agent.objects.create(fullname='Real', email='real@example.com', mobile='9000000002',
                                       status='pending_approval', plan_type='starter',
                                       referred_by_code=self.participant.referral_code)
        register_referred_agent(genuine)
        qualify_event_referral(genuine, _paid_sub(genuine))
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.paid_count, 1)

    def _admin_post(self, view, **post):
        request = RequestFactory().post('/admin/event-referral/x/', post)
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch('apps.event_referral.views.admin_views._get_admin_from_session', return_value=1):
            return view(request, self.participant.pk)

    def test_admin_extend_deadline_works(self):
        from apps.event_referral.views.admin_views import admin_extend_deadline
        before = self.participant.deadline_at
        resp = self._admin_post(admin_extend_deadline, extend_hours='12')
        self.assertEqual(resp.status_code, 302)
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.deadline_at, before + timedelta(hours=12))

    def test_admin_restore_unblocks_participant(self):
        from apps.event_referral.views.admin_views import admin_restore_participant
        self.participant.status = EventReferralParticipant.STATUS_BLOCKED
        self.participant.save()
        resp = self._admin_post(admin_restore_participant, extend_hours='0')
        self.assertEqual(resp.status_code, 302)
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.status, EventReferralParticipant.STATUS_ACTIVE)

    def test_admin_restore_keeps_winner_and_approved_agent(self):
        from apps.event_referral.views.admin_views import admin_restore_participant
        self.participant.status = EventReferralParticipant.STATUS_WON
        self.participant.save()
        self.referrer.status, self.referrer.plan_type = 'active', 'basic'
        self.referrer.save()
        self._admin_post(admin_restore_participant, extend_hours='0')
        self.participant.refresh_from_db()
        self.referrer.refresh_from_db()
        self.assertEqual(self.participant.status, EventReferralParticipant.STATUS_WON)
        self.assertEqual(self.referrer.status, 'active')
