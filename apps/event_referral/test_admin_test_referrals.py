"""Admin test tool for the Paldi challenge: fake paid referrals, local (DEBUG)
only, counted through the real qualification path."""
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings

from apps.agents.models import Agent, AgentSubscription
from apps.event_referral.models import EventReferral, EventReferralCampaign, EventReferralParticipant
from apps.event_referral.views import admin_views


class AdminTestReferralToolTests(TestCase):
    def setUp(self):
        EventReferralCampaign.objects.all().delete()
        self.campaign = EventReferralCampaign.objects.create(is_enabled=True, required_paid_referrals=2, window_hours=48)
        self.referrer = Agent.objects.create(fullname='Challenger', email='challenger.t@example.com',
                                             mobile='9000000601', status='event_challenge', plan_type='')
        self.participant = EventReferralParticipant.create_for_agent(self.referrer, self.campaign)

    def _post(self, view, **post):
        request = RequestFactory().post('/admin/event-referral/x/', post)
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch('apps.event_referral.views.admin_views._get_admin_from_session', return_value=1):
            resp = view(request, self.participant.pk)
        self.participant.refresh_from_db()
        self.referrer.refresh_from_db()
        return resp, [str(m) for m in request._messages]

    @override_settings(DEBUG=True)
    def test_fake_referrals_count_win_and_can_be_removed(self):
        resp, msgs = self._post(admin_views.admin_test_add_referrals, count='1')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual((self.participant.paid_count, self.participant.status), (1, 'active'))
        self._post(admin_views.admin_test_add_referrals, count='1')
        self.assertEqual(self.participant.paid_count, 2)
        self.assertEqual(self.participant.status, EventReferralParticipant.STATUS_WON)
        self.assertEqual((self.referrer.status, self.referrer.plan_type), ('pending_approval', 'basic'))
        fakes = Agent.objects.filter(email__endswith='@paldi-test.invalid')
        self.assertEqual(fakes.count(), 2)
        self.assertTrue(all(a.mobile != self.referrer.mobile for a in fakes))

        _, msgs = self._post(admin_views.admin_test_remove_referrals)
        self.assertEqual(self.participant.paid_count, 0)
        # Deleted, or (if a legacy table blocks the cascade) detached and marked deleted.
        self.assertFalse(Agent.objects.filter(email__endswith='@paldi-test.invalid')
                         .exclude(status='deleted').exists())
        self.assertFalse(Agent.objects.filter(referred_by_code=self.participant.referral_code).exists())
        self.assertFalse(AgentSubscription.objects.filter(razorpay_order_id__startswith='order_TESTREF').exists())
        self.assertFalse(EventReferral.objects.filter(participant=self.participant).exists())

        # The win is now no longer earned, so Restore undoes it.
        self._post(admin_views.admin_restore_participant, extend_hours='0')
        self.assertEqual(self.participant.status, EventReferralParticipant.STATUS_ACTIVE)
        self.assertEqual((self.referrer.status, self.referrer.plan_type), ('event_challenge', ''))

    @override_settings(DEBUG=True)
    def test_count_is_capped_at_ten(self):
        self.participant.required_paid_referrals = 50
        self.participant.save(update_fields=['required_paid_referrals'])
        self._post(admin_views.admin_test_add_referrals, count='99')
        self.assertEqual(self.participant.paid_count, 10)

    @override_settings(DEBUG=False)
    def test_not_available_on_the_live_site(self):
        for view in (admin_views.admin_test_add_referrals, admin_views.admin_test_remove_referrals):
            with self.assertRaises(Http404):
                self._post(view, count='1')
        self.assertEqual(self.participant.paid_count, 0)

    def _dashboard_html(self):
        request = RequestFactory().get('/admin/event-referral/')
        request.session = {}
        with patch('apps.event_referral.views.admin_views._get_admin_from_session', return_value=1), \
             patch('apps.admin_panel.context_processors.admin_badge_counts', return_value={}):
            return admin_views.admin_dashboard(request).content.decode()

    @override_settings(DEBUG=False)
    def test_buttons_hidden_on_the_live_site(self):
        self.assertNotIn('+ Test referral', self._dashboard_html())

    @override_settings(DEBUG=True)
    def test_buttons_shown_locally(self):
        html = self._dashboard_html()
        self.assertIn('+ Test referral', html)
        self.assertIn('Remove test', html)
