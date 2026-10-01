"""The Paldi signup signs the person in, so it must only continue an existing
account for that account's own signed-in owner (security audit 2026-10-02 H1)."""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from apps.agents.models import Agent
from apps.event_referral.models import EventReferralCampaign, EventReferralParticipant
from apps.home.models.pincode import Pincode

EMAIL = 'apps.agents.services.brevo.email_service'


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class PaldiExistingAccountRequiresLoginTests(TestCase):
    def setUp(self):
        Pincode.objects.create(pincode='380001', office_name='Ahmedabad GPO', district='Ahmedabad',
                               state='Gujarat', latitude='23.0', longitude='72.5')
        EventReferralCampaign.objects.all().delete()
        EventReferralCampaign.objects.create(is_enabled=True, required_paid_referrals=2, window_hours=48)

    def _form(self, email, mobile, name='Some Person'):
        return {'fullname': name, 'email': email, 'mobile': mobile, 'whatsapp': mobile,
                'agent_pincode': '380001', 'state': 'Gujarat', 'experience_range': '3',
                'segments[]': ['life'], 'client_base': '100', 'agree_terms': 'on'}

    def _paldi_post(self, client, data):
        client.get('/48HR/')
        with patch(EMAIL):
            return client.post('/agent-register-step1/', data)

    def _existing(self, status, email, mobile):
        user = User.objects.create_user(email, email, 'pw')
        return Agent.objects.create(fullname='Real Owner', email=email, mobile=mobile,
                                    agent_pincode='380001', status=status, user=user)

    def test_existing_accounts_are_not_continued_without_signing_in(self):
        for i, status in enumerate(('pending_payment', 'incomplete', 'rejected', 'event_challenge')):
            with self.subTest(status=status):
                email, mobile = f'owner{i}@example.com', f'900000071{i}'
                agent = self._existing(status, email, mobile)
                client = Client()
                resp = self._paldi_post(client, self._form(email, f'900000072{i}', name='Other Name'))
                self.assertEqual(resp.status_code, 422, resp.content)
                self.assertEqual(resp.json().get('redirect'), '/agent-login/')
                self.assertNotIn('_auth_user_id', client.session)
                agent.refresh_from_db()
                self.assertEqual((agent.fullname, agent.mobile, agent.status),
                                 ('Real Owner', mobile, status))

    def test_new_people_still_join(self):
        resp = self._paldi_post(Client(), self._form('brand.new@example.com', '9000000703'))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(EventReferralParticipant.objects.filter(agent__email='brand.new@example.com').exists())
