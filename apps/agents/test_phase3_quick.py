"""Regression tests for phase-3 quick audit fixes (PAY9, PAY15, AG4, AG12, AG15, AG16, AG20)."""

from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.admin_panel.models.users import User as LaravelUser
from apps.agents.models import Agent, AgentLead, AgentNotification, PromoCode
from password_hashing import hash_password


class SyncVerifiedPasswordKeepsPortalRoleTests(TestCase):
    """PAY9: an agent login must not rewrite a distributor's `users.role`."""

    def test_distributor_role_survives_agent_login_sync(self):
        from apps.agents.services.account_auth import sync_verified_password

        LaravelUser.objects.create(
            fullname="Dist",
            email="dual@example.com",
            password=hash_password("Secret123"),
            role="distributor",
            status="active",
        )
        sync_verified_password("dual@example.com", "Dist", "Secret123", role="agent")
        self.assertEqual(
            LaravelUser.objects.get(email="dual@example.com").role, "distributor"
        )

    def test_agent_role_still_written_for_plain_users_row(self):
        from apps.agents.services.account_auth import sync_verified_password

        LaravelUser.objects.create(
            fullname="A",
            email="plain@example.com",
            password=hash_password("Secret123"),
            role="user",
            status="active",
        )
        sync_verified_password("plain@example.com", "A", "Secret123", role="agent")
        self.assertEqual(
            LaravelUser.objects.get(email="plain@example.com").role, "agent"
        )


class PromoUsageCapTests(TestCase):
    """PAY15: the usage counter never passes max_uses."""

    def test_increment_stops_at_max_uses(self):
        from apps.agents.views.registration import _increment_promo_usage

        PromoCode.objects.create(
            code="CAP2",
            discount_type="percentage",
            discount_value=10,
            max_uses=2,
            times_used=1,
        )
        _increment_promo_usage("CAP2")
        _increment_promo_usage("CAP2")
        self.assertEqual(PromoCode.objects.get(code="CAP2").times_used, 2)

    def test_unlimited_code_still_counts(self):
        from apps.agents.views.registration import _increment_promo_usage

        PromoCode.objects.create(
            code="NOCAP", discount_type="percentage", discount_value=10
        )
        _increment_promo_usage("NOCAP")
        self.assertEqual(PromoCode.objects.get(code="NOCAP").times_used, 1)


class _SyncThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._t, self._a, self._k = target, args, kwargs or {}

    def start(self):
        self._t(*self._a, **self._k)


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
@patch("apps.wa_agent_bot.services.notification_service.notify_agent_new_lead")
class CaptureLeadTests(TestCase):
    """AG4 / AG20: escaped lead email, per-IP+agent cap, dashboard link from site base."""

    def setUp(self):
        cache.clear()
        self.agent = Agent.objects.create(
            fullname="Lead Agent",
            email="lead.agent@example.com",
            mobile="9876500111",
            status="active",
        )

    def _post(self, mobile, name="Ravi"):
        return self.client.post(
            reverse("agents:agent_leads_capture"),
            {
                "agent_id": self.agent.pk,
                "interaction_type": "call",
                "fullname": name,
                "email": "c@example.com",
                "mobile": mobile,
            },
        )

    @patch(
        "apps.agents.services.og_urls.get_public_site_base",
        return_value="https://site.test",
    )
    def test_lead_email_escapes_customer_fields(self, _base, _notify):
        with (
            patch("threading.Thread", _SyncThread),
            patch("apps.agents.services.brevo.email_service") as svc,
        ):
            resp = self._post("9000000001", name="<script>x</script>")
        self.assertTrue(resp.json()["success"])
        html = svc.send_generic.call_args[0][3]
        self.assertNotIn("<script>x</script>", html)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", html)
        self.assertIn('href="https://site.test/agent-login/"', html)

    @patch("threading.Thread", MagicMock())
    def test_leads_capped_per_ip_and_agent(self, _notify):
        for i in range(5):
            self.assertTrue(self._post(f"900000010{i}").json()["success"])
        resp = self._post("9000000199").json()
        self.assertTrue(resp["success"])
        self.assertTrue(resp.get("duplicate"))
        self.assertEqual(resp["url"], "tel:9876500111")
        self.assertEqual(AgentLead.objects.filter(agent=self.agent).count(), 5)


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class EventPromoRateLimitTests(TestCase):
    """AG12: the event promo check uses the signup promo limiter."""

    def test_pauses_after_too_many_wrong_codes(self):
        from apps.agents.views.registration import PROMO_FAIL_LIMIT

        cache.clear()
        PromoCode.objects.create(
            code="EVREAL", discount_type="percentage", discount_value=10
        )
        url = reverse("events:verify.promo")
        for i in range(PROMO_FAIL_LIMIT):
            self.assertEqual(
                self.client.post(url, {"promo_code": f"BAD{i}"}).status_code, 200
            )
        self.assertEqual(
            self.client.post(url, {"promo_code": "EVREAL"}).status_code, 429
        )


class CareerTimelineAdminWithoutAgentTests(TestCase):
    """AG16: admin session without agent_id gets 404 JSON, not a 500."""

    def test_admin_without_agent_id(self):
        with patch("apps.admin_panel.auth._get_admin_from_session", return_value=1):
            resp = self.client.get(reverse("agents:agent_career_timeline_suggestions"))
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["status"], "error")


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class DashboardNotificationsReadTests(TestCase):
    """AG15: only the listed notifications are marked read."""

    def test_notification_created_after_listing_stays_unread(self):
        from apps.agents.test_audit_security import _paid_agent

        agent = _paid_agent(email="notif@example.com", mobile="9876500222")
        user = agent.user
        shown = AgentNotification.objects.create(agent=agent, title="old", body="b")
        real_filter = AgentNotification.objects.filter
        late = {}

        def filter_then_insert(*args, **kwargs):
            qs = real_filter(*args, **kwargs)
            if kwargs.get("is_read") is False and not late:
                listed = list(qs.order_by("-created_at"))
                late["row"] = AgentNotification.objects.create(
                    agent=agent, title="new", body="b"
                )
                stub = MagicMock()
                stub.order_by.return_value = listed
                return stub
            return qs

        self.client.force_login(user)
        with patch.object(
            AgentNotification.objects, "filter", side_effect=filter_then_insert
        ):
            self.client.get(reverse("agents:agent_dashboard"))
        self.assertIn("row", late)
        self.assertTrue(AgentNotification.objects.get(pk=shown.pk).is_read)
        self.assertFalse(AgentNotification.objects.get(pk=late["row"].pk).is_read)
