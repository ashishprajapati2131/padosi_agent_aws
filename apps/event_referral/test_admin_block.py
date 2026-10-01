"""Admin "Block" on the Event Referral page crashed in production
(TypeError: unexpected keyword 'by_admin'). An admin block now suspends the
challenger's login; Restore undoes it; a deadline block is unchanged."""
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, TestCase, override_settings

from apps.agents.models import Agent
from apps.event_referral.models import EventReferralCampaign, EventReferralParticipant
from apps.event_referral.services.participant_service import evaluate_participant, event_referral_grants_dashboard
from apps.event_referral.views import admin_views
from password_hashing import hash_password


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class AdminBlockTests(TestCase):
    def setUp(self):
        EventReferralCampaign.objects.all().delete()
        campaign = EventReferralCampaign.objects.create(is_enabled=True, required_paid_referrals=5, window_hours=48)
        self.user = User.objects.create_user('blocked.c@example.com', 'blocked.c@example.com')
        self.user.password = hash_password('9000001401')
        self.user.save()
        self.agent = Agent.objects.create(fullname='Challenger', email='blocked.c@example.com', mobile='9000001401',
                                          status='event_challenge', plan_type='', user=self.user)
        self.participant = EventReferralParticipant.create_for_agent(self.agent, campaign)

    def _admin(self, view, **post):
        request = RequestFactory().post('/admin/event-referral/x/', post)
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch('apps.event_referral.views.admin_views._get_admin_from_session', return_value=1):
            resp = view(request, self.participant.pk)
        self.participant.refresh_from_db()
        self.agent.refresh_from_db()
        return resp

    def _login(self):
        client = Client()
        client.post('/agent-login/', {'email': 'blocked.c@example.com', 'password': '9000001401'})
        return client

    def test_admin_block_suspends_and_restore_brings_back(self):
        resp = self._admin(admin_views.admin_block_participant, reason='Fake referrals')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.participant.status, EventReferralParticipant.STATUS_BLOCKED)
        self.assertTrue(self.participant.blocked_by_admin)
        self.assertEqual(self.agent.status, 'suspended')
        self.assertFalse(event_referral_grants_dashboard(self.agent))
        self.assertNotIn('_auth_user_id', self._login().session)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, 'suspended')       # login did not re-open it

        self._admin(admin_views.admin_restore_participant, extend_hours='24')
        self.assertEqual(self.participant.status, EventReferralParticipant.STATUS_ACTIVE)
        self.assertFalse(self.participant.blocked_by_admin)
        self.assertEqual(self.agent.status, 'event_challenge')
        self.assertIn('_auth_user_id', self._login().session)

    def test_admin_block_never_suspends_a_paid_or_approved_agent(self):
        Agent.objects.filter(pk=self.agent.pk).update(status='active')
        self._admin(admin_views.admin_block_participant)
        self.assertEqual(self.agent.status, 'active')

    def test_deadline_block_is_unchanged(self):
        self.participant.deadline_at = datetime.now() - timedelta(minutes=1)
        self.participant.save(update_fields=['deadline_at'])
        evaluate_participant(self.participant, block_on_expire=True)
        self.participant.refresh_from_db()
        self.agent.refresh_from_db()
        self.assertEqual(self.participant.status, EventReferralParticipant.STATUS_BLOCKED)
        self.assertFalse(self.participant.blocked_by_admin)
        self.assertEqual(self.agent.status, 'pending_payment')
        self.assertTrue(event_referral_grants_dashboard(self.agent))
