"""Admin panel audit 2026-11-07, Phase 1 (data safety): B2, B4, B18, S5, S7."""

import json
from unittest.mock import patch

from django.contrib.auth.models import User as AuthUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.admin_panel.models.admin_auth import Admin
from apps.admin_panel.models.user_session import UserSession
from apps.admin_panel.models.users import User as LaravelUser
from apps.agents.models import Agent, AgentSubscription, Invoice


class AgentEmailChangeTests(TestCase):  # B2
    def setUp(self):
        self.agent = Agent.objects.create(
            fullname="A",
            email="a.agent@example.com",
            mobile="9000000301",
            status="active",
        )
        AuthUser.objects.create_user("staff.login", "taken@example.com", "x")

    def _update(self, email):
        from apps.admin_panel.views.agents import update_profile

        request = RequestFactory().post(
            "/admin/agents/update-profile/",
            {
                "id": self.agent.pk,
                "fullname": "A",
                "email": email,
                "mobile": "9000000301",
            },
        )
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch(
            "apps.admin_panel.views.agents._get_admin_from_session", return_value=1
        ):
            return update_profile(request)

    def test_email_owned_by_another_login_is_rejected(self):
        self._update("taken@example.com")
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.email, "a.agent@example.com")


class AgentDeleteKeepsUnreconciledOrdersTests(TestCase):  # B4
    def test_pending_row_with_real_order_is_soft_deleted(self):
        from apps.admin_panel.views.delete import admin_delete

        agent = Agent.objects.create(
            fullname="P",
            email="p.del@example.com",
            mobile="9000000302",
            status="pending_payment",
        )
        sub = AgentSubscription.objects.create(
            agent=agent,
            selected_plan="Starter's Plan",
            registration_amount="2359.00",
            payment_status="pending",
            status="inactive",
            razorpay_order_id="order_PENDINGDEL001",
        )
        request = RequestFactory().post(
            "/admin/delete/",
            data=json.dumps({"model": "agent", "id": agent.pk}),
            content_type="application/json",
        )
        request.session = {}
        with patch(
            "apps.admin_panel.views.delete._get_admin_from_session", return_value=1
        ):
            body = json.loads(admin_delete(request).content)
        self.assertTrue(body["success"], body)
        agent.refresh_from_db()
        self.assertEqual(agent.status, "deleted")
        self.assertTrue(AgentSubscription.objects.filter(pk=sub.pk).exists())


class ManualInvoiceDuplicateTests(TestCase):  # B18
    def test_second_invoice_for_same_payment_is_rejected(self):
        from apps.admin_panel.views.invoices import create_manual_invoice

        agent = Agent.objects.create(
            fullname="I", email="i@example.com", mobile="9000000303", status="active"
        )
        Invoice.objects.create(
            invoice_number="PA/DUP/1",
            agent=agent,
            agent_name="I",
            agent_email="i@example.com",
            plan_name="Starter's Plan",
            plan_type="manual",
            base_amount="2000.00",
            gst_amount="359.00",
            total_amount="2359.00",
            discount_folder="no_discount",
            razorpay_payment_id="pay_DUPLICATE0001",
        )
        request = RequestFactory().post(
            "/admin/invoices/create/",
            {
                "name": "I",
                "email": "i@example.com",
                "plan_name": "Starter's Plan",
                "base_amount": "2000",
                "gst_amount": "359",
                "total_amount": "2359",
                "razorpay_payment_id": "pay_DUPLICATE0001",
            },
        )
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch(
            "apps.admin_panel.views.invoices._get_admin_from_session", return_value=1
        ):
            create_manual_invoice(request)
        self.assertEqual(
            Invoice.objects.filter(razorpay_payment_id="pay_DUPLICATE0001").count(), 1
        )

    def test_negative_amount_is_rejected(self):
        from apps.admin_panel.views.invoices import create_manual_invoice

        request = RequestFactory().post(
            "/admin/invoices/create/",
            {
                "name": "N",
                "email": "n@example.com",
                "plan_name": "Starter's Plan",
                "base_amount": "-10",
                "gst_amount": "0",
                "total_amount": "-10",
            },
        )
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch(
            "apps.admin_panel.views.invoices._get_admin_from_session", return_value=1
        ):
            create_manual_invoice(request)
        self.assertFalse(Invoice.objects.filter(agent_email="n@example.com").exists())


class UserCredentialEditTests(TestCase):  # S5
    def setUp(self):
        self.user = LaravelUser.objects.create(
            fullname="U",
            email="u@example.com",
            password="$2y$10$old",
            role="client",
            status="active",
        )

    def _update(self, is_super, **extra):
        from apps.admin_panel.views.users import user_update

        data = {
            "fullname": "U",
            "email": "u@example.com",
            "role": "client",
            "status": "active",
            **extra,
        }
        request = RequestFactory().post(f"/admin/users/{self.user.pk}/update/", data)
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with (
            patch(
                "apps.admin_panel.views.users._get_admin_from_session", return_value=1
            ),
            patch(
                "apps.admin_panel.views.pages._is_super_admin", return_value=is_super
            ),
        ):
            user_update(request, self.user.pk)
        return request

    def test_staff_cannot_set_password_and_password_is_not_kept_in_session(self):
        request = self._update(
            False, password="newpassword1", password_confirmation="newpassword1"
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, "$2y$10$old")
        self.assertNotIn("password", request.session.get("form_old", {}))

    def test_super_admin_can_set_password(self):
        self._update(
            True, password="newpassword1", password_confirmation="newpassword1"
        )
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.password, "$2y$10$old")


class AdminPasswordResetRevokesSessionsTests(TestCase):  # S7
    def test_other_sessions_are_deleted(self):
        from apps.admin_panel.views.admins import admins_update

        target = Admin.objects.create(
            name="T", email="t@example.com", password="x", role="staff"
        )
        UserSession.objects.create(session_token="stolen-token", admin_id=target.pk)
        UserSession.objects.create(session_token="my-token", admin_id=target.pk)
        request = RequestFactory().post(
            f"/admin/admins/{target.pk}/update/",
            {
                "name": "T",
                "email": "t@example.com",
                "role": "staff",
                "password": "newpassword1",
                "password_confirmation": "newpassword1",
            },
        )
        request.COOKIES["session_token"] = "my-token"
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch(
            "apps.admin_panel.views.admins._get_admin_from_session",
            return_value=target.pk,
        ):
            admins_update(request, target.pk)
        self.assertEqual(
            list(
                UserSession.objects.filter(admin_id=target.pk).values_list(
                    "session_token", flat=True
                )
            ),
            ["my-token"],
        )


class AdminLoginAccountLockTests(TestCase):  # S6 (audit 2026-11-07)
    def _login(self, email, password="wrong-password"):
        from apps.admin_panel.views.dashboard import admin_login
        request = RequestFactory().post("/admin/login/post/", {"email": email, "password": password})
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch("apps.admin_panel.views.dashboard._record_failed_admin_login"), \
             patch("apps.admin_panel.views.dashboard.render", side_effect=lambda req, tpl, ctx=None: ctx or {}):
            return admin_login(request)

    def test_account_locks_after_repeated_failures(self):
        from django.core.cache import cache
        from apps.admin_panel.views.dashboard import ADMIN_LOGIN_MAX_FAILS
        cache.delete("admin_login_fail_locked@example.com")
        Admin.objects.create(name="L", email="locked@example.com", password="$2b$04$abcdefghijklmnopqrstuuJ1v3QpZ0zZ9n6r7wQv9yQkqH5y3nHq", role="staff")
        for _ in range(ADMIN_LOGIN_MAX_FAILS):
            self.assertEqual(self._login("locked@example.com")["error"], "Invalid email or password.")
        self.assertIn("Too many failed attempts", self._login("locked@example.com")["error"])

    def test_unknown_email_gets_the_same_message(self):
        self.assertEqual(self._login("nobody@example.com")["error"], "Invalid email or password.")


class MediumBugFixTests(TestCase):  # audit 2026-11-07: B13, B16, B21, B22, B23
    def test_parse_int(self):
        from apps.admin_panel.parsing import parse_int
        self.assertEqual((parse_int("3", 1), parse_int("abc", 1), parse_int(None, 1)), (3, 1, 1))

    def test_starter_target_includes_basic_agents(self):  # B16
        from apps.admin_panel.services.broadcast_service import target_agents
        a = Agent.objects.create(fullname="B", email="basic.t@example.com", mobile="9000000401", status="active", plan_type="basic")
        b = Agent.objects.create(fullname="S", email="starter.t@example.com", mobile="9000000402", status="active", plan_type="Starter")
        Agent.objects.create(fullname="P", email="pro.t@example.com", mobile="9000000403", status="active", plan_type="professional")
        self.assertEqual(set(target_agents("starter").values_list("id", flat=True)), {a.id, b.id})

    def test_double_approve_runs_once(self):  # B21
        from apps.admin_panel.views.agents import toggle_status
        agent = Agent.objects.create(fullname="D", email="dbl@example.com", mobile="9000000404", status="pending_approval")

        def call():
            request = RequestFactory().post("/admin/agents/toggle-status/", data=json.dumps({"id": agent.pk, "status": "active"}),
                                            content_type="application/json")
            SessionMiddleware(lambda r: None).process_request(request)
            request._messages = FallbackStorage(request)
            with patch("apps.admin_panel.views.agents._get_admin_from_session", return_value=1), \
                 patch("apps.admin_panel.views.agents._admin_can_manage_all_agents", return_value=True):
                return toggle_status(request)

        with patch("apps.admin_panel.views.agents.connection") as conn:
            # Second request saw the old status but the row already changed: UPDATE matches nothing.
            cur = conn.cursor.return_value.__enter__.return_value
            cur.fetchone.return_value = ("pending_approval",)
            cur.rowcount = 0
            self.assertEqual(call().status_code, 409)

    def test_fcm_returns_zero_when_not_configured(self):  # B23
        from django.test import override_settings
        from apps.agents.services.fcm import FcmService
        with override_settings(FCM_PROJECT_ID="", FCM_SERVICE_ACCOUNT_JSON=""):
            self.assertEqual(FcmService().send_to_tokens(["t"], "x", "y"), 0)


class AccountDeletionMatchingTests(TestCase):  # B9 (audit 2026-11-07)
    def test_request_with_someone_elses_mobile_does_not_terminate_them(self):
        from apps.agents.models import AccountDeletionRequest
        from apps.admin_panel.views.account_deletion import terminate_agent_account
        victim = Agent.objects.create(fullname="V", email="victim@example.com", mobile="9000000501", status="active")
        req = AccountDeletionRequest.objects.create(reference_id="DEL-B9-1", identifier="9000000501",
                                                    email="attacker@example.com", mobile="9000000501")
        request = RequestFactory().post("/admin/account-deletion/terminate/",
                                        data=json.dumps({"request_id": req.pk}), content_type="application/json")
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch("apps.admin_panel.views.account_deletion._get_admin_from_session", return_value=1):
            terminate_agent_account(request)
        victim.refresh_from_db()
        self.assertEqual(victim.status, "active")
