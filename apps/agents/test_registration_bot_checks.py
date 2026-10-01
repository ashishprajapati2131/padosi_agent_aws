"""Light bot checks on registration: hidden honeypot field, minimum time
between showing the form and posting it, and a per-network hourly cap on
new Paldi challengers. Security audit 2026-10-02 M2."""
import time
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, override_settings

from apps.agents.models import AgentDraft
from apps.agents.signup_test_support import _SignupBase
from apps.agents.views.registration import REG_FORM_SHOWN_AT_KEY
from apps.event_referral.models import EventReferralCampaign, EventReferralParticipant
from apps.home.models import SiteSetting


class RegistrationBotCheckTests(_SignupBase):
    def _form(self, email, mobile, **extra):
        data = {'fullname': 'Real Person', 'email': email, 'mobile': mobile,
                'agent_pincode': '380001', 'state': 'Gujarat', 'experience_range': '3',
                'segments[]': ['life']}
        data.update(extra)
        return data

    def test_honeypot_filled_is_refused(self):
        r = self.client.post('/agent-register-step1/', self._form('bot1@example.com', '9000001001', website='http://spam'))
        self.assertEqual(r.status_code, 400)
        self.assertFalse(AgentDraft.objects.filter(email='bot1@example.com').exists())

    def test_empty_honeypot_is_fine(self):
        r = self.client.post('/agent-register-step1/', self._form('human1@example.com', '9000001002', website=''))
        self.assertTrue(r.json()['success'], r.content)

    def test_registration_page_contains_the_hidden_field(self):
        html = self.client.get('/agent-registration/').content.decode()
        self.assertIn('name="website"', html)

    @override_settings(TESTING=False, REGISTRATION_MIN_FILL_SECONDS=3)
    def test_instant_post_after_showing_form_is_refused(self):
        self.client.get('/agent-registration/')
        r = self.client.post('/agent-register-step1/', self._form('fast@example.com', '9000001003'))
        self.assertEqual(r.status_code, 429)
        session = self.client.session
        session[REG_FORM_SHOWN_AT_KEY] = int(time.time()) - 30   # a person took 30 seconds
        session.save()
        r = self.client.post('/agent-register-step1/', self._form('fast@example.com', '9000001003'))
        self.assertTrue(r.json()['success'], r.content)

    def test_paldi_new_signups_per_network_are_capped(self):
        cache.clear()
        EventReferralCampaign.objects.all().delete()
        EventReferralCampaign.objects.create(is_enabled=True, required_paid_referrals=2, window_hours=48)
        SiteSetting.set_value('paldi_signups_per_ip_per_hour', '2', 'event')
        results = []
        for i in range(3):
            client = Client()
            client.get('/event-registration/')
            with patch('apps.agents.services.brevo.email_service'):
                r = client.post('/agent-register-step1/', self._form(f'stall{i}@example.com', f'900000110{i}'))
            results.append(r.status_code)
        self.assertEqual(results, [200, 200, 429])
        self.assertEqual(EventReferralParticipant.objects.count(), 2)
