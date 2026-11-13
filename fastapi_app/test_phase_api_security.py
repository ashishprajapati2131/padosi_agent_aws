"""API audit fixes: API5 (sync auth endpoints), API11/12 (WAF), API13/20 (deletion OTP), API19 (dead auth code)."""

import hashlib
import inspect
import time
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from fastapi_app.middleware import threat_monitor as tm
from fastapi_app.routers import account_deletion as ad


def _fake_db(count=0):
    db = MagicMock()
    q = db.query.return_value.filter.return_value
    q.count.return_value = count
    q.first.return_value = None
    return db


class WafTests(unittest.TestCase):
    def test_template_pattern_still_matches_and_is_bounded(self):
        self.assertEqual(
            tm._match_threat("{{ 7*7 }}", "", False), "Server-Side Template Injection"
        )
        self.assertEqual(
            tm._match_threat("x {% if 1 %} y", "", False),
            "Server-Side Template Injection",
        )
        started = time.monotonic()
        tm._match_threat("{{" + " a" * 30000 + "{%" + " b" * 30000, "", False)
        self.assertLess(time.monotonic() - started, 1.0)

    def _inspect(self, db, user, auth="Bearer t"):
        with (
            patch.object(tm, "SessionLocal", return_value=db),
            patch.object(tm, "_blocked_ips", return_value={}),
            patch.object(tm, "_authenticated_user", return_value=user),
            patch.object(tm, "_send_alert_email"),
            patch.object(tm.settings, "WAF_AUTO_BAN_ENABLED", True),
        ):
            return tm._inspect_request(
                "203.0.113.50", "select * from x", "http://t/api/v1/x", auth, "ua"
            )

    def _added(self, db):
        return [type(c.args[0]).__name__ for c in db.add.call_args_list]

    def test_unauthenticated_third_hit_bans(self):
        db = _fake_db(count=2)
        self.assertEqual(self._inspect(db, None, auth=None)[0], 403)
        self.assertEqual(self._added(db), ["BlockedIp", "SecurityThreatLog"])

    def test_authenticated_hit_is_logged_but_never_bans(self):
        db = _fake_db(count=5)
        user = MagicMock(fullname="App User", email="app.user@example.com")
        self.assertEqual(self._inspect(db, user)[0], 403)
        self.assertEqual(self._added(db), ["SecurityThreatLog"])
        self.assertEqual(db.add.call_args.args[0].hacker_email, "app.user@example.com")

    def test_blocked_ip_set_is_cached_and_invalidated(self):
        db = MagicMock()
        db.query.return_value.all.return_value = [
            MagicMock(ip_address="198.51.100.9", reason="manual", created_at=None)
        ]
        tm._invalidate_blocked_ips()
        with patch.object(tm, "SessionLocal", return_value=db):
            self.assertIn("198.51.100.9", tm._blocked_ips())
            tm._blocked_ips()
            self.assertEqual(db.query.call_count, 1)
            tm._invalidate_blocked_ips()
            tm._blocked_ips()
            self.assertEqual(db.query.call_count, 2)
            verdict = tm._inspect_request(
                "198.51.100.9", "", "http://t/api/x", None, "ua"
            )
        tm._invalidate_blocked_ips()
        self.assertEqual(verdict[0], 403)


class DeletionOtpTests(unittest.TestCase):
    def test_otp_hash_is_keyed_not_static_salt(self):
        old = hashlib.sha256(b"padosi_del_salt_2026_123456").hexdigest()
        self.assertEqual(ad._hash_otp("123456"), ad._hash_otp("123456"))
        self.assertNotEqual(ad._hash_otp("123456"), old)

    def test_clock_is_naive_local(self):
        now = ad._now()
        self.assertIsNone(now.tzinfo)
        self.assertLess(
            abs((now - __import__("datetime").datetime.now()).total_seconds()), 5
        )

    def test_failed_email_returns_503_and_never_logs_otp(self):
        agent = MagicMock(id=1, user_id=2, mobile="9876543210", pan_number="ABCDE1234F")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = agent
        payload = MagicMock(
            email="del.user@example.com",
            mobile="9876543210",
            pan_number="ABCDE1234F",
            fullname="Del User",
            reason="other",
            comments="",
        )
        req = MagicMock(headers={})
        with (
            patch(
                "apps.agents.services.brevo.email_service.send_generic",
                return_value=False,
            ),
            patch(
                "fastapi_app.services.email_service.EmailService._send_brevo_http_sync",
                return_value=False,
            ),
            patch.object(ad, "_get_client_ip", return_value="203.0.113.1"),
            patch.object(ad.secrets, "randbelow", return_value=123456 - 100000),
            self.assertLogs("account_deletion", level="INFO") as logs,
        ):
            with self.assertRaises(HTTPException) as ctx:
                ad.request_deletion_otp(payload, req, db)
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertNotIn("123456", "\n".join(logs.output))


class DeadAuthCodeAndSyncEndpointTests(unittest.TestCase):
    def test_dead_helpers_removed(self):
        import fastapi_app.dependencies.auth as dep
        import fastapi_app.utils.auth as ua

        self.assertFalse(hasattr(dep, "require_admin"))
        self.assertFalse(hasattr(ua, "create_refresh_token"))

    def test_forgot_password_runs_in_threadpool(self):
        from fastapi_app.routers.auth import forgot_password

        self.assertFalse(inspect.iscoroutinefunction(forgot_password))

        async def fake(request, req):
            return "sent"

        service = MagicMock(send_reset_link=fake)
        self.assertEqual(forgot_password(MagicMock(), MagicMock(), service), "sent")


if __name__ == "__main__":
    unittest.main()
