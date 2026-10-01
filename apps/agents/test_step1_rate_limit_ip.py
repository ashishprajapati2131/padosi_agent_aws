"""Audit 2026-10-01 F-29: the step-1 registration rate limit keyed on the first
X-Forwarded-For hop, which the client controls: changing it reset the limit,
and setting it to someone else's IP locked them out of registration."""
from django.core.cache import cache
from django.test import TestCase, override_settings


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class Step1RateLimitIpTests(TestCase):
    def setUp(self):
        cache.clear()

    def _post(self, forwarded_for):
        # Behind the local proxy (REMOTE_ADDR 127.0.0.1) Apache appends the real
        # client IP as the right-most hop; the client can only prepend values.
        # (Public addresses: TEST-NET ranges count as private and are skipped.)
        return self.client.post('/agent-register-step1/', {}, HTTP_X_FORWARDED_FOR=forwarded_for,
                                REMOTE_ADDR='127.0.0.1')

    def test_spoofed_first_hop_does_not_reset_the_limit(self):
        for i in range(20):
            self.assertNotEqual(self._post(f'10.0.0.{i}, 49.36.10.5').status_code, 429)
        self.assertEqual(self._post('10.9.9.9, 49.36.10.5').status_code, 429)

    def test_a_spoofed_victim_ip_is_not_locked_out(self):
        for _ in range(20):
            self._post('106.51.20.30, 49.36.10.5')   # attacker claims the victim's IP
        self.assertNotEqual(self._post('106.51.20.30').status_code, 429)  # the real victim
