"""Audit 2026-10-01 F-30: mobile API login had only an in-process per-IP limit,
so one account's password could be guessed from many IPs. It now shares the
website's per-account limit (10 failures / 15 minutes)."""
import json
from itertools import count
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import SimpleTestCase

from password_hashing import hash_password


class ApiLoginAccountThrottleTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        from fastapi_app.services import auth_service
        auth_service.login_attempts_store.clear()
        self.auth_service = auth_service
        self.user = MagicMock(email='api.agent@example.com', password=hash_password('Right@Pass1'),
                              role='agent', id=9, status='active')
        self.ips = (f'198.51.100.{n}' for n in count(1))

    def _login(self, password):
        from fastapi_app.schemas.auth import LoginRequest
        repo = MagicMock()
        repo.get_by_email.return_value = self.user
        agent_repo = MagicMock()
        agent_repo.get_by_email.return_value = MagicMock(status='active', email=self.user.email)
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None  # no auth_user fallback row
        service = self.auth_service.AuthService(repo, agent_repo, db)
        with patch('fastapi_app.utils.client_ip.get_client_ip', return_value=next(self.ips)), \
             patch.object(self.auth_service, 'generate_and_register_token', return_value='tok'):
            resp = service.login(LoginRequest(email=self.user.email, password=password), MagicMock())
        return resp.status_code, json.loads(resp.body)

    def test_failures_from_many_ips_lock_the_account(self):
        for _ in range(10):
            self.assertEqual(self._login('wrong')[0], 401)
        code, body = self._login('Right@Pass1')   # new IP, correct password: still limited
        self.assertEqual(code, 429, body)

    def test_success_clears_the_counter(self):
        for _ in range(5):
            self._login('wrong')
        self.assertNotEqual(self._login('Right@Pass1')[0], 429)
        for _ in range(9):
            self.assertEqual(self._login('wrong')[0], 401)  # counter restarted
