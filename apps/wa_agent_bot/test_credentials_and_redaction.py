"""The credentials reply must send a reset link, not claim mobile = password, and the message log
must redact password lines (audit WA2/WA3)."""
import unittest
from unittest.mock import MagicMock

from apps.wa_agent_bot.services.message_sender import _redact
from apps.wa_agent_bot.services.post_login_handler import handle_credentials


class CredentialsReplyTests(unittest.TestCase):
    def test_no_password_or_mobile_in_reply(self):
        agent = MagicMock(email='demo@example.com', mobile='9876543210', fullname='Demo')
        reply = handle_credentials(agent)
        self.assertNotIn('9876543210', reply)
        self.assertNotIn('*Password:*', reply)
        self.assertIn('password-reset', reply.lower())


class MessageRedactionTests(unittest.TestCase):
    def test_password_lines_are_redacted(self):
        text = "Welcome\nPassword: `abc123`\nAll set"
        self.assertNotIn('abc123', _redact(text))
        self.assertIn('[redacted]', _redact(text))

    def test_other_lines_untouched(self):
        self.assertEqual(_redact('Hi friend'), 'Hi friend')
