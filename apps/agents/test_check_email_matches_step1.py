"""The email check on the registration form said "available" for agents that
step 1 then refuses (e.g. a Paldi challenger signing up again from another
device), so the preview opened and "Claim" failed behind it."""
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from apps.agents.models import Agent


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class CheckEmailMatchesStep1Tests(TestCase):
    def _check(self, email, client=None):
        return (client or Client()).get('/agent-check-email/', {'email': email}).json()

    def _agent(self, email, status, user=None):
        return Agent.objects.create(fullname='C', email=email, mobile='9000000501', status=status, user=user)

    def test_challenger_from_another_device_is_told_to_login(self):
        self._agent('ch@example.com', 'event_challenge')
        data = self._check('ch@example.com')
        self.assertTrue(data['registered'])
        self.assertIn('Please login', data['message'])
        self.assertEqual(data['login_url'], '/agent-login/')

    def test_challenger_in_own_session_is_not_blocked(self):
        user = User.objects.create_user('own@example.com', 'own@example.com', 'x')
        self._agent('own@example.com', 'event_challenge', user=user)
        client = Client()
        client.force_login(user)
        self.assertFalse(self._check('own@example.com', client)['registered'])

    def test_in_progress_registrations_stay_available(self):
        for i, status in enumerate(('incomplete', 'pending_payment', 'rejected')):
            self._agent(f'inprog{i}@example.com', status)
            self.assertFalse(self._check(f'inprog{i}@example.com')['registered'], status)

    def test_blocked_accounts_get_the_support_message(self):
        self._agent('sus@example.com', 'suspended')
        data = self._check('sus@example.com')
        self.assertTrue(data['registered'])
        self.assertIn('contact support', data['message'])

    def test_active_and_unknown_emails_unchanged(self):
        self._agent('act@example.com', 'active')
        self.assertTrue(self._check('act@example.com')['registered'])
        self.assertFalse(self._check('nobody@example.com')['registered'])
