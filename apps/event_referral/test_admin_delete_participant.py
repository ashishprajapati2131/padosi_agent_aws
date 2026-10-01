"""Super Admin "Delete" on the Event Referral page: removes a challenger
(e.g. a test signup) from the event, the leaderboards and, when it has no
real payment or invoice, the account itself."""
import time
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings

from apps.admin_panel.models import User as LaravelUser
from apps.agents.models import Agent, AgentDraft, AgentSubscription
from apps.event_referral.models import EventReferral, EventReferralCampaign, EventReferralParticipant
from apps.event_referral.services.public_leaderboard import get_public_leaderboard_payload
from apps.event_referral.views import admin_views
from apps.home.models import SiteSetting
from apps.referral_championship.models import ChampionshipParticipant

SUPER = SimpleNamespace(role='super')
STAFF = SimpleNamespace(role='staff')


@override_settings(DEBUG=False, ALLOWED_HOSTS=['testserver', 'localhost'])
class AdminDeleteParticipantTests(TestCase):
    def setUp(self):
        cache.clear()
        EventReferralCampaign.objects.all().delete()
        self.campaign = EventReferralCampaign.objects.create(is_enabled=True, required_paid_referrals=5, window_hours=48)

    def _challenger(self, email, mobile, staff=False):
        user = User.objects.create_user(email, email, 'pw', is_staff=staff)
        LaravelUser.objects.create(fullname='T', email=email, password='x', role='agent', status='active')
        agent = Agent.objects.create(fullname='Test Challenger', email=email, mobile=mobile,
                                     status='event_challenge', plan_type='', user=user)
        AgentDraft.objects.create(session_key='s', email=email, fullname='Test Challenger', mobile=mobile)
        return agent, EventReferralParticipant.create_for_agent(agent, self.campaign)

    def _post(self, view, admin, participant, **post):
        request = RequestFactory().post('/admin/event-referral/x/', post)
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        request.admin_user = admin
        with patch('apps.event_referral.views.admin_views._get_admin_from_session', return_value=1):
            return view(request, participant.pk)

    def test_test_challenger_is_removed_everywhere(self):
        agent, participant = self._challenger('test.challenger@example.com', '9000001601')
        SiteSetting.set_value(admin_views.TEST_MODE_SETTING, str(int(time.time()) + 3600), 'event')
        self._post(admin_views.admin_test_add_referrals, SUPER, participant, count='3')
        self.assertTrue(ChampionshipParticipant.objects.filter(agent=agent).exists())
        self.assertEqual(len(get_public_leaderboard_payload()['leaderboard']), 1)

        resp = self._post(admin_views.admin_delete_participant, SUPER, participant)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(EventReferralParticipant.objects.filter(pk=participant.pk).exists())
        self.assertFalse(EventReferral.objects.exists())
        # Deleted, or hidden as 'deleted' when a legacy table blocks the cascade
        # (the test DB's agent_notifications copy does).
        self.assertFalse(Agent.objects.filter(email='test.challenger@example.com').exclude(status='deleted').exists())
        self.assertFalse(Agent.objects.filter(email__endswith='@paldi-test.invalid').exclude(status='deleted').exists())
        self.assertFalse(User.objects.filter(email='test.challenger@example.com', is_active=True).exists())
        self.assertFalse(LaravelUser.objects.filter(email='test.challenger@example.com').exists())
        self.assertFalse(AgentDraft.objects.filter(email='test.challenger@example.com').exists())
        self.assertFalse(ChampionshipParticipant.objects.filter(agent_id=agent.pk).exists())
        cache.clear()
        self.assertEqual(get_public_leaderboard_payload()['leaderboard'], [])

    def test_agent_with_real_payment_is_kept(self):
        agent, participant = self._challenger('real.paid@example.com', '9000001602')
        AgentSubscription.objects.create(agent=agent, selected_plan="Starter's Plan", registration_amount='2359.00',
                                         payment_status='completed', status='active',
                                         razorpay_order_id='order_REALPAID000001', razorpay_payment_id='pay_REALPAID0000001')
        self._post(admin_views.admin_delete_participant, SUPER, participant)
        self.assertFalse(EventReferralParticipant.objects.filter(pk=participant.pk).exists())
        agent.refresh_from_db()
        self.assertEqual(agent.status, 'event_challenge')
        self.assertTrue(User.objects.filter(email='real.paid@example.com').exists())

    def test_staff_login_is_never_deleted(self):
        agent, participant = self._challenger('staff.person@example.com', '9000001603', staff=True)
        self._post(admin_views.admin_delete_participant, SUPER, participant)
        self.assertFalse(Agent.objects.filter(pk=agent.pk).exclude(status='deleted').exists())
        self.assertTrue(User.objects.filter(email='staff.person@example.com', is_active=True).exists())

    def test_only_a_super_admin_can_delete(self):
        agent, participant = self._challenger('keep.me@example.com', '9000001604')
        with self.assertRaises(Http404):
            self._post(admin_views.admin_delete_participant, STAFF, participant)
        self.assertTrue(EventReferralParticipant.objects.filter(pk=participant.pk).exists())
