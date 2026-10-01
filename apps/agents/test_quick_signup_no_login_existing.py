"""Passwordless lead sign-ups (Facebook ad form, quick register) must not
sign in an account that already exists: typing an email proves nothing.
New accounts created by the request are still signed in.
Security audit 2026-10-02 L4."""
import json

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from apps.home.models.pincode import Pincode


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class QuickSignupExistingAccountTests(TestCase):
    def setUp(self):
        Pincode.objects.create(pincode='380001', office_name='Ahmedabad GPO', district='Ahmedabad',
                               state='Gujarat', latitude='23.0', longitude='72.5')
        self.existing = User.objects.create_user('client.old', 'client.old@example.com', None)

    def _post(self, url, email, mobile='9000000801'):
        client = Client()
        resp = client.post(url, data=json.dumps({
            'fullname': 'Lead Person', 'name': 'Lead Person', 'email': email,
            'mobile': mobile, 'pincode': '380001',
        }), content_type='application/json')
        return client, resp

    def test_existing_account_is_not_signed_in(self):
        for url in ('/join/ad/', '/client/quick-register/'):
            with self.subTest(url=url):
                client, resp = self._post(url, 'client.old@example.com')
                self.assertEqual(resp.status_code, 200, resp.content)
                self.assertTrue(resp.json().get('success'), resp.content)
                self.assertNotIn('_auth_user_id', client.session)
                self.assertEqual(client.session['quick_lead_user']['mobile'], '9000000801')

    def test_new_account_is_still_signed_in(self):
        for i, url in enumerate(('/join/ad/', '/client/quick-register/')):
            with self.subTest(url=url):
                email = f'client.new{i}@example.com'
                client, resp = self._post(url, email, mobile=f'900000081{i}')
                self.assertEqual(resp.status_code, 200, resp.content)
                user = User.objects.get(email=email)
                self.assertEqual(str(client.session.get('_auth_user_id')), str(user.pk))
