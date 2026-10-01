"""The promo check pauses after repeated wrong codes, so codes cannot be
guessed by trying many (security audit 2026-10-02 M3)."""
import json

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from apps.agents.models import PromoCode
from apps.agents.views.registration import PROMO_FAIL_LIMIT


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class PromoVerifyRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        PromoCode.objects.create(code='REALCODE', discount_type='percentage', discount_value=10)

    def _verify(self, client, code):
        return client.post('/agent/verify-promo/', data=json.dumps({'promo_code': code}),
                           content_type='application/json')

    def test_valid_code_works(self):
        resp = self._verify(Client(), 'REALCODE')
        self.assertTrue(resp.json()['success'])

    def test_checks_pause_after_too_many_wrong_codes(self):
        client = Client()
        for i in range(PROMO_FAIL_LIMIT):
            self.assertEqual(self._verify(client, f'WRONG{i}').status_code, 200)
        resp = self._verify(client, 'REALCODE')
        self.assertEqual(resp.status_code, 429)
        self.assertFalse(resp.json()['success'])
        # A new browser from the same network is paused too (per-IP count).
        self.assertEqual(self._verify(Client(), 'WRONGX').status_code, 429)

    def test_a_few_typos_are_fine(self):
        client = Client()
        for i in range(3):
            self._verify(client, f'TYPO{i}')
        self.assertTrue(self._verify(client, 'REALCODE').json()['success'])
