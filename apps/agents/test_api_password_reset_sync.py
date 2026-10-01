"""Audit 2026-10-01 F-08: a mobile-API password reset updated only `users`,
so the old password still worked through Django's `auth_user` (web login
accepts either store; API login copied it back)."""
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from password_hashing import check_password_hash, hash_password


class ApiPasswordResetSyncTests(SimpleTestCase):
    def _reset(self, current_agent=None, token=None):
        from fastapi_app.schemas.auth import ResetPasswordRequest
        from fastapi_app.services.password_reset_service import PasswordResetService

        own = MagicMock(email='me@example.com', password=hash_password('Old@Pass123'), id=7)
        db = MagicMock()
        service = PasswordResetService(db)
        service.user_repo = MagicMock()
        service.user_repo.get_by_email.side_effect = lambda e: own if (e or '').lower() == 'me@example.com' else None
        service.token_repo = MagicMock()
        service.token_repo.get_valid_token_record.return_value = MagicMock(token=hash_password('tok123'))
        resp = service.reset_password(
            ResetPasswordRequest(token=token, email='me@example.com',
                                 password='New@Pass1234', password_confirmation='New@Pass1234'),
            None, current_agent=current_agent,
        )
        return resp, own, db

    def _auth_user_updates(self, db):
        return [c for c in db.execute.call_args_list if 'UPDATE auth_user' in str(c.args[0])]

    def test_emailed_token_reset_also_updates_auth_user(self):
        resp, own, db = self._reset(token='tok123')
        self.assertEqual(resp.status_code, 200, resp.body)
        self.assertTrue(check_password_hash('New@Pass1234', own.password))
        updates = self._auth_user_updates(db)
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].args[1], {'password': own.password, 'email': 'me@example.com'})
        db.commit.assert_called_once()

    def test_in_app_change_also_updates_auth_user(self):
        resp, own, db = self._reset(current_agent=MagicMock(email='me@example.com'))
        self.assertEqual(resp.status_code, 200, resp.body)
        updates = self._auth_user_updates(db)
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].args[1]['password'], own.password)

    def test_bad_token_changes_nothing(self):
        resp, own, db = self._reset(token='wrong')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self._auth_user_updates(db), [])
        self.assertTrue(check_password_hash('Old@Pass123', own.password))
