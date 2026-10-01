"""One mobile number, one account: a number already used by an agent with a
different email cannot start another registration or Paldi challenge.
Security audit 2026-10-02 L3."""
from unittest.mock import patch

from django.test import Client

from apps.agents.models import Agent
from apps.agents.signup_test_support import _SignupBase
from apps.event_referral.models import EventReferralCampaign, EventReferralParticipant


class OneMobileOneAccountTests(_SignupBase):
    def setUp(self):
        super().setUp()
        Agent.objects.create(fullname='First', email='first.owner@example.com', mobile='9000000901',
                             status='pending_approval')

    def test_same_mobile_with_another_email_is_refused(self):
        r = self._step1('second.person@example.com', mobile='9000000901')
        self.assertEqual(r.status_code, 422, r.content)
        self.assertIn('mobile', r.json().get('errors', {}))
        self.assertNotIn('first.owner', r.content.decode())       # other email not revealed
        self.assertFalse(Agent.objects.filter(email='second.person@example.com').exists())

    def test_same_mobile_refused_on_the_paldi_page(self):
        EventReferralCampaign.objects.all().delete()
        EventReferralCampaign.objects.create(is_enabled=True, required_paid_referrals=2, window_hours=48)
        client = Client()
        client.get('/48HR/')
        with patch('apps.agents.services.brevo.email_service'):
            r = client.post('/agent-register-step1/', {
                'fullname': 'Second', 'email': 'paldi.second@example.com', 'mobile': '9000000901',
                'agent_pincode': '380001', 'state': 'Gujarat', 'experience_range': '3',
                'segments[]': ['life'],
            })
        self.assertEqual(r.status_code, 422, r.content)
        self.assertFalse(EventReferralParticipant.objects.filter(agent__email='paldi.second@example.com').exists())

    def test_new_mobile_and_own_resume_still_work(self):
        self.assertTrue(self._step1('fresh.person@example.com', mobile='9000000902').json()['success'])
        # Same email + same mobile again (resuming) is not blocked by this rule.
        self.assertTrue(self._step1('fresh.person@example.com', mobile='9000000902').json()['success'])

    def test_deleted_account_frees_its_mobile(self):
        Agent.objects.filter(email='first.owner@example.com').update(status='deleted')
        self.assertTrue(self._step1('reuse.after.delete@example.com', mobile='9000000901').json()['success'])
