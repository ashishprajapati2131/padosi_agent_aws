"""End-to-end flows (real URLs, real session, middleware included) for admin modules that had
no tests: plans, coming soon, referrals, notifications, broadcasts. Audit 2026-11-07."""

from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.db import connection
from django.test import TestCase

from apps.admin_panel.models import AdminBroadcast
from apps.admin_panel.models.admin_auth import Admin
from apps.agents.models import Agent, AgentDeviceToken, AgentNotification


class AdminFlowTestCase(TestCase):
    def setUp(self):
        self.admin = Admin.objects.create(
            name="Flow", email="flow@example.com", password="x", role="super"
        )
        now = datetime.now()
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO user_sessions (session_token, admin_id, last_activity, expires_at, created_at, updated_at)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                ["flow-token", self.admin.pk, now, now + timedelta(days=1), now, now],
            )
            sid = cursor.lastrowid
            cursor.execute(
                "INSERT INTO user_session_data (session_id, data_key, data_value, created_at, updated_at)"
                " VALUES (%s, 'admin_id', %s, %s, %s)",
                [sid, str(self.admin.pk), now, now],
            )
        self.client.cookies["session_token"] = "flow-token"

    def messages_of(self, response):
        return [str(m) for m in get_messages(response.wsgi_request)]


class PlanFlowTests(AdminFlowTestCase):
    def test_create_then_rename_keeps_slug(self):
        from apps.agents.models import SubscriptionPlan

        self.client.post(
            "/admin/plans/add/",
            {
                "name": "Gold Plan",
                "actual_price": "999",
                "discounted_price": "799",
                "sort_order": "1",
                "is_active": "on",
            },
        )
        plan = SubscriptionPlan.objects.get(name="Gold Plan")
        self.assertEqual(plan.slug, "gold-plan")
        self.client.post(
            f"/admin/plans/{plan.pk}/edit/",
            {
                "name": "Gold Plus",
                "actual_price": "999",
                "discounted_price": "799",
                "sort_order": "1",
            },
        )
        plan.refresh_from_db()
        self.assertEqual(
            (plan.name, plan.slug), ("Gold Plus", "gold-plan")
        )  # B20: slug fixed

    def test_bad_sort_order_does_not_crash(self):
        response = self.client.post(
            "/admin/plans/add/", {"name": "Bad", "sort_order": "abc"}
        )
        self.assertNotEqual(response.status_code, 500)


class ComingSoonFlowTests(AdminFlowTestCase):
    def test_create_toggle_delete_feature(self):
        from apps.home.models.upcoming_feature import UpcomingFeature

        r = self.client.post(
            "/admin/coming-soon/feature/save/",
            {"title": "Smart Leads", "description": "d", "is_active": "1"},
        )
        self.assertEqual(r.status_code, 200, r.content)
        feature = UpcomingFeature.objects.get(title="Smart Leads")
        before = feature.is_active
        self.client.post(f"/admin/coming-soon/feature/{feature.pk}/toggle/")
        feature.refresh_from_db()
        self.assertNotEqual(feature.is_active, before)
        self.client.post(f"/admin/coming-soon/feature/{feature.pk}/delete/")
        self.assertFalse(UpcomingFeature.objects.filter(pk=feature.pk).exists())

    def test_title_is_required(self):
        r = self.client.post("/admin/coming-soon/feature/save/", {"title": ""})
        self.assertEqual(r.status_code, 400)


class ReferralFlowTests(AdminFlowTestCase):
    def test_non_numeric_tiers_are_rejected_without_saving(self):
        r = self.client.post(
            "/admin/referrals/update-tiers/",
            {"tier1_min": "five", "tier2_min": "10", "tier3_min": "15"},
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(any("whole numbers" in m for m in self.messages_of(r)))


class NotifyFlowTests(AdminFlowTestCase):
    def setUp(self):
        super().setUp()
        self.agent = Agent.objects.create(
            fullname="N",
            email="n.flow@example.com",
            mobile="9000000701",
            status="active",
        )

    def test_send_without_device_saves_the_notification(self):
        r = self.client.post(
            "/admin/agent/notifications/send/",
            {"agent_id": self.agent.pk, "title": "Hi", "body": "B"},
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(
            AgentNotification.objects.filter(
                agent_id=self.agent.pk, title="Hi"
            ).exists()
        )

    def test_zero_delivered_pushes_warn_instead_of_success(self):  # B23
        AgentDeviceToken.objects.create(agent=self.agent, token="tok-1")
        with patch(
            "apps.agents.services.fcm.FcmService.send_to_tokens", return_value=0
        ):
            r = self.client.post(
                "/admin/agent/notifications/send/",
                {"agent_id": self.agent.pk, "title": "Hi", "body": "B"},
            )
        self.assertTrue(any("no push was delivered" in m for m in self.messages_of(r)))


class BroadcastFlowTests(AdminFlowTestCase):
    def test_send_records_broadcast_and_queues_the_right_agents(self):  # B15/B16
        basic = Agent.objects.create(
            fullname="B",
            email="b.flow@example.com",
            mobile="9000000702",
            status="active",
            plan_type="basic",
        )
        Agent.objects.create(
            fullname="P",
            email="p.flow@example.com",
            mobile="9000000703",
            status="active",
            plan_type="professional",
        )
        with patch("apps.admin_panel.views.broadcast.queue_broadcast") as queued:
            r = self.client.post(
                "/admin/broadcast/send/",
                {
                    "target": "starter",
                    "subject": "S",
                    "message": "M",
                    "channels": ["email"],
                },
            )
        self.assertEqual(r.status_code, 302)
        row = AdminBroadcast.objects.get(subject="S")
        self.assertEqual(queued.call_args.args[:2], (row.pk, [basic.pk]))

    def test_delivery_counts_real_sends(self):
        from apps.admin_panel.services.broadcast_service import deliver_broadcast

        a = Agent.objects.create(
            fullname="A",
            email="a.flow@example.com",
            mobile="9000000704",
            status="active",
        )
        row = AdminBroadcast.objects.create(
            subject="S", message="Hi {name}", target="all", channels="email"
        )
        with patch(
            "apps.admin_panel.services.brevo.send_brevo_email", return_value=True
        ) as sent:
            deliver_broadcast(row.pk, [a.pk], "S", "Hi {name}", ["email"], "all")
        row.refresh_from_db()
        self.assertEqual(row.sent_count, 1)
        self.assertIn("A", sent.call_args.args[3])  # name personalised

    def test_missing_fields_are_rejected(self):
        r = self.client.post(
            "/admin/broadcast/send/",
            {"target": "starter", "subject": "", "message": "M"},
        )
        self.assertEqual(r.status_code, 302)
        self.assertFalse(AdminBroadcast.objects.exists())
