"""Production-readiness fixes: webhook amount mismatch acks without activating;
the cron trigger token never falls back to SECRET_KEY."""

import json
import os
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class WebhookAmountMismatchTests(TestCase):
    @patch("apps.agents.views.registration.queue_invoice_and_welcome")
    def test_amount_mismatch_returns_200_and_does_not_activate(self, _queue):
        from apps.agents.models import Agent, AgentSubscription

        agent = Agent.objects.create(
            fullname="Mismatch",
            email="mismatch.wh@example.com",
            mobile="9000000931",
            status="pending_payment",
        )
        sub = AgentSubscription.objects.create(
            agent=agent,
            selected_plan="Starter",
            registration_amount=1179,
            payment_status="pending",
            status="inactive",
            razorpay_order_id="order_MISMATCH0001",
        )
        client = MagicMock()
        body = json.dumps(
            {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_MISMATCH0001",
                            "order_id": "order_MISMATCH0001",
                            "amount": 100,
                            "status": "captured",
                        }
                    }
                },
            }
        )
        with (
            patch(
                "apps.agents.views.registration.razorpay_client", return_value=client
            ),
            patch(
                "apps.agents.views.registration.razorpay_webhook_secret",
                return_value="whsec",
            ),
            self.assertLogs("apps.agents.views.registration", level="ERROR"),
        ):
            resp = self.client.post(
                "/razorpay-webhook/",
                data=body,
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE="sig",
            )
        self.assertEqual(resp.status_code, 200)
        sub.refresh_from_db()
        agent.refresh_from_db()
        self.assertEqual(sub.payment_status, "pending")
        self.assertEqual(agent.status, "pending_payment")


class CronTokenTests(SimpleTestCase):
    def _call(self, **headers):
        from apps.admin_panel.views.system import run_maintenance_jobs

        request = RequestFactory().get("/admin/system/run-jobs/", **headers)
        request.user = AnonymousUser()
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with (
            patch(
                "apps.agents.services.background_jobs.retry_missing_invoices",
                return_value=0,
            ),
            patch("django.core.management.call_command"),
        ):
            return run_maintenance_jobs(request)

    def test_secret_key_prefix_is_not_a_token(self):
        with (
            patch.dict(os.environ, {"CRON_TRIGGER_TOKEN": ""}),
            override_settings(CRON_TRIGGER_TOKEN=""),
        ):
            self.assertEqual(
                self._call(HTTP_X_CRON_TOKEN=settings.SECRET_KEY[:24]).status_code, 403
            )

    def test_configured_token_accepted_via_header_only(self):
        with override_settings(CRON_TRIGGER_TOKEN="cron-tok-123"):
            self.assertEqual(
                self._call(HTTP_X_CRON_TOKEN="cron-tok-123").status_code, 200
            )
            # Audit 2026-11-07 S11: a token in the URL leaks into access logs, so it is ignored.
            self.assertNotEqual(
                self._call(QUERY_STRING="token=cron-tok-123").status_code, 200
            )
            self.assertEqual(self._call(HTTP_X_CRON_TOKEN="wrong").status_code, 403)
