from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.http import HttpResponseRedirect
from django.test import SimpleTestCase
from django.urls import reverse

from apps.agents.services.account_auth import verify_agent_password
from password_hashing import check_password_hash, hash_password


class PasswordHashingTests(SimpleTestCase):
    def test_bcrypt_roundtrip_matches_admin_login(self):
        stored = hash_password('secret-pass')
        self.assertTrue(stored.startswith(('$2b$', '$2a$', '$2y$')))
        self.assertTrue(check_password_hash('secret-pass', stored))
        self.assertFalse(check_password_hash('wrong-pass', stored))

    def test_laravel_2y_prefix_is_accepted(self):
        stored = hash_password('secret-pass')
        laravel = '$2y$' + stored[4:]
        self.assertTrue(check_password_hash('secret-pass', laravel))

    def test_legacy_django_pbkdf2_still_verifies(self):
        stored = make_password('legacy-pass', hasher='pbkdf2_sha256')
        self.assertTrue(stored.startswith('pbkdf2_'))
        self.assertTrue(check_password_hash('legacy-pass', stored))
        self.assertFalse(check_password_hash('nope', stored))


class VerifyAgentPasswordTests(SimpleTestCase):
    @patch('apps.agents.services.account_auth.find_django_user', return_value=None)
    @patch('apps.agents.services.account_auth.fetch_users_row', return_value=None)
    def test_orphan_pending_agent_accepts_email_as_temp_password(self, _lu, _du):
        email = 'coderparth2587@gmail.com'
        agent = SimpleNamespace(email=email, status='pending_payment')
        ok, _, _ = verify_agent_password(email, email, agent=agent)
        self.assertTrue(ok)

    @patch('apps.agents.services.account_auth.find_django_user', return_value=None)
    @patch('apps.agents.services.account_auth.fetch_users_row', return_value=None)
    def test_orphan_pending_agent_rejects_other_password(self, _lu, _du):
        email = 'coderparth2587@gmail.com'
        agent = SimpleNamespace(email=email, status='pending_payment')
        ok, _, _ = verify_agent_password(email, 'not-the-email', agent=agent)
        self.assertFalse(ok)

    @patch('apps.agents.services.account_auth.find_django_user', return_value=None)
    @patch('apps.agents.services.account_auth.fetch_users_row')
    def test_users_table_bcrypt_is_used_like_admin(self, mock_lu, _du):
        password = 'MyBcryptPass1'
        mock_lu.return_value = SimpleNamespace(
            email='active.agent@example.com',
            password=hash_password(password),
            role='agent',
        )
        agent = SimpleNamespace(email='active.agent@example.com', status='active')
        ok, _, _ = verify_agent_password(agent.email, password, agent=agent)
        self.assertTrue(ok)
        ok_wrong, _, _ = verify_agent_password(agent.email, 'wrong', agent=agent)
        self.assertFalse(ok_wrong)


class AgentLoginViewTests(SimpleTestCase):
    def setUp(self):
        self.login_url = reverse('agents:agent_login')

    @patch('apps.agents.views.auth.agent_can_access_dashboard', return_value=False)
    @patch('apps.agents.views.auth.login')
    @patch('apps.agents.views.registration.verify_and_activate_pending_payment', return_value=False)
    @patch('apps.agents.views.auth.sync_verified_password')
    @patch('apps.agents.views.auth.verify_agent_password')
    @patch('apps.agents.views.auth.find_agent')
    def test_pending_payment_without_capture_goes_to_chooseplan(
        self, mock_agent, mock_verify, mock_sync, _verify_pay, _mock_login, _can_dash
    ):
        email = 'coderparth2587@gmail.com'
        mock_agent.return_value = SimpleNamespace(
            email=email,
            fullname='Piyush bhai sadhu',
            status='pending_payment',
            refresh_from_db=lambda: None,
        )
        django_user = SimpleNamespace(email=email, is_authenticated=True)
        mock_verify.return_value = (True, None, django_user)
        mock_sync.return_value = django_user

        response = self.client.post(self.login_url, {
            'email': email,
            'password': email,
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('agents:chooseplan'))

    @patch('apps.agents.views.auth.agent_can_access_dashboard', return_value=True)
    @patch('apps.agents.views.auth._finish_agent_session_login', return_value=HttpResponseRedirect('/agent/dashboard/'))
    @patch('apps.agents.views.auth.sync_verified_password')
    @patch('apps.agents.views.auth.verify_agent_password')
    @patch('apps.agents.views.auth.find_agent')
    def test_active_agent_valid_password_goes_to_dashboard(
        self, mock_agent, mock_verify, mock_sync, mock_finish, _can_dash
    ):
        email = 'active.agent@example.com'
        mock_agent.return_value = SimpleNamespace(
            email=email,
            fullname='Active Agent',
            status='active',
            refresh_from_db=lambda: None,
        )
        django_user = SimpleNamespace(email=email)
        mock_verify.return_value = (True, None, django_user)
        mock_sync.return_value = django_user

        response = self.client.post(self.login_url, {
            'email': email,
            'password': 'correct-password',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/agent/dashboard/')
        mock_finish.assert_called_once()

    @patch('apps.agents.views.auth.find_agent', side_effect=RuntimeError('db down'))
    def test_lookup_exception_stays_on_login(self, _find):
        response = self.client.post(self.login_url, {
            'email': 'anyone@example.com',
            'password': 'whatever',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Login service is temporarily unavailable')

    @patch('apps.agents.views.auth.find_laravel_user', return_value=None)
    @patch('apps.agents.views.auth.find_agent')
    @patch('apps.agents.views.auth.verify_agent_password', return_value=(False, None, None))
    def test_invalid_password_shows_generic_error(self, _verify, mock_agent, _lu):
        mock_agent.return_value = SimpleNamespace(
            email='coderparth2587@gmail.com',
            status='pending_payment',
        )
        response = self.client.post(self.login_url, {
            'email': 'coderparth2587@gmail.com',
            'password': 'wrong-password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please Enter Valid Login Details')
