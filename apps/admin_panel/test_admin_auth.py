from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock
from password_hashing import hash_password
from apps.admin_panel.views.dashboard import _mask_email, ADMIN_SESSION_COOKIE
from apps.admin_panel.context_processors import admin_badge_counts


class AdminAuthTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_mask_email(self):
        self.assertEqual(_mask_email("admin@padosiagent.com"), "a***n@padosiagent.com")
        self.assertEqual(_mask_email("ab@padosiagent.com"), "a*@padosiagent.com")
        self.assertEqual(_mask_email("a@padosiagent.com"), "a*@padosiagent.com")
        self.assertEqual(_mask_email(""), "")
        self.assertEqual(_mask_email(None), "")

    def test_badge_counts_skips_login_and_logout(self):
        class DummyRequest:
            def __init__(self, path):
                self.path = path
                self.COOKIES = {}

        for path in ['/admin', '/admin/login', '/admin/login/', '/admin/login/post', '/admin/login/post/', '/admin/logout', '/admin/logout/']:
            req = DummyRequest(path)
            self.assertEqual(admin_badge_counts(req), {}, f"Failed on {path}")

    def test_get_admin_login_page_renders_successfully(self):
        response = self.client.get(reverse('admin_login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PadosiAgent Admin")
        self.assertContains(response, "Sign In")

    def test_get_admin_login_page_via_alias(self):
        response = self.client.get(reverse('admin_login_page'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign In")

    def test_admin_login_post_empty_credentials(self):
        response = self.client.post(reverse('admin_login_post'), {'email': '', 'password': ''})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email and password are required.")

    @patch('apps.admin_panel.views.dashboard.connection')
    def test_admin_login_post_invalid_email(self, mock_conn):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        response = self.client.post(reverse('admin_login_post'), {
            'email': 'nonexistent@example.com',
            'password': 'anypassword',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid email or password.")

    @patch('apps.admin_panel.views.dashboard.connection')
    def test_admin_login_post_invalid_password(self, mock_conn):
        mock_cursor = MagicMock()
        stored_hash = hash_password("correct-secret")
        mock_cursor.fetchone.return_value = (1, stored_hash)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        response = self.client.post(reverse('admin_login_post'), {
            'email': 'admin@example.com',
            'password': 'wrong-password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid email or password.")

    @patch('apps.admin_panel.views.dashboard.connection')
    def test_admin_login_post_success_without_mfa(self, mock_conn):
        mock_cursor = MagicMock()
        stored_hash = hash_password("correct-secret")
        mock_cursor.fetchone.return_value = (1, stored_hash)
        mock_cursor.lastrowid = 123
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        response = self.client.post(reverse('admin_login_post'), {
            'email': 'admin@example.com',
            'password': 'correct-secret',
        })
        # Should redirect to admin_dashboard on success
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('admin_dashboard'))
        self.assertIn(ADMIN_SESSION_COOKIE, response.cookies)

    @patch('apps.admin_panel.services.brevo.send_otp_email')
    @patch('apps.admin_panel.views.dashboard.connection')
    def test_admin_login_post_mfa_flow(self, mock_conn, mock_send_email):
        mock_send_email.return_value = True
        mock_cursor = MagicMock()
        stored_hash = hash_password("correct-secret")
        mock_cursor.fetchone.return_value = (42, stored_hash)
        mock_cursor.lastrowid = 456
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        with self.settings(ADMIN_MFA_ENABLED=True):
            # Step 1: Submit email & password -> gets MFA prompt
            resp = self.client.post(reverse('admin_login_post'), {
                'email': 'admin@padosiagent.com',
                'password': 'correct-secret',
            })
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "Two-Factor Authentication")
            self.assertContains(resp, "a***n@padosiagent.com")
            mfa_ticket = resp.context['mfa_ticket']
            self.assertTrue(mfa_ticket)

            # Step 2: Submit wrong OTP
            resp_wrong = self.client.post(reverse('admin_login_post'), {
                'mfa_ticket': mfa_ticket,
                'otp': '000000',
            })
            self.assertEqual(resp_wrong.status_code, 200)
            self.assertContains(resp_wrong, "Invalid verification code.")

            # Step 3: Fetch cached OTP and submit correct OTP
            from django.core.cache import cache
            session_data = cache.get(f"admin_mfa_{mfa_ticket}")
            correct_otp = session_data['otp']

            resp_correct = self.client.post(reverse('admin_login_post'), {
                'mfa_ticket': mfa_ticket,
                'otp': correct_otp,
            })
            self.assertEqual(resp_correct.status_code, 302)
            self.assertEqual(resp_correct.url, reverse('admin_dashboard'))
            self.assertIn(ADMIN_SESSION_COOKIE, resp_correct.cookies)
