"""Event checkout orders are fulfilled by the Razorpay webhook / recovery as well
as the browser callback, exactly once (one invoice + welcome)."""

import hashlib
import hmac
import json
from datetime import date
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.agents.models import Agent, AgentSubscription, Event, EventRegistration

ORDER = "order_EVTWEBHOOK001"
PAYMENT = "pay_EVTWEBHOOK001"
BASIC_PAISE = 235882  # 1999 + 18% GST
RZP_SECRET = "evt_test_secret"


def _payment(amount=BASIC_PAISE, status="captured"):
    return {
        "id": PAYMENT,
        "order_id": ORDER,
        "amount": amount,
        "status": status,
        "currency": "INR",
    }


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost"], RAZORPAY_SECRET=RZP_SECRET
)
@patch("apps.agents.views.events._event_razorpay_client", return_value=None)
@patch("apps.agents.services.post_payment.queue_invoice_and_welcome")
class EventWebhookFulfilmentTests(TestCase):
    @classmethod
    def setUpClass(cls):
        # event_registrations is unmanaged and its migration state predates the
        # event FK, so the SQLite test table lacks event_id: add it (no migration).
        from django.db import connection

        with connection.cursor() as cursor:
            columns = [
                c.name
                for c in connection.introspection.get_table_description(
                    cursor, "event_registrations"
                )
            ]
        if "event_id" not in columns:
            with connection.schema_editor() as editor:
                editor.add_field(
                    EventRegistration, EventRegistration._meta.get_field("event")
                )
        super().setUpClass()

    def setUp(self):
        event = Event.objects.create(name="Expo", event_date=date.today())
        self.agent = Agent.objects.create(
            fullname="Event Payer",
            email="event.payer@example.com",
            mobile="9000000951",
            status="pending_payment",
            plan_type="basic",
        )
        self.sub = AgentSubscription.objects.create(
            agent=self.agent,
            selected_plan="Starter",
            registration_amount=2358.82,
            payment_status="pending",
            status="inactive",
            razorpay_order_id=ORDER,
        )
        self.reg = EventRegistration.objects.create(
            event=event,
            fullname="Event Payer",
            email=self.agent.email,
            mobile="9000000951",
            selected_plan="basic",
            razorpay_order_id=ORDER,
        )

    def _webhook(self, payment):
        client = MagicMock()
        body = json.dumps(
            {"event": "payment.captured", "payload": {"payment": {"entity": payment}}}
        )
        with (
            patch(
                "apps.agents.views.registration.razorpay_client", return_value=client
            ),
            patch(
                "apps.agents.views.registration.razorpay_webhook_secret",
                return_value="whsec",
            ),
        ):
            return self.client.post(
                "/razorpay-webhook/",
                data=body,
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE="sig",
            )

    def _browser(self):
        session = self.client.session
        session["current_event_registration_id"] = self.reg.pk
        session.save()
        signature = hmac.new(
            RZP_SECRET.encode(), f"{ORDER}|{PAYMENT}".encode(), hashlib.sha256
        ).hexdigest()
        return self.client.post(
            "/events/payment/success/",
            {
                "razorpay_order_id": ORDER,
                "razorpay_payment_id": PAYMENT,
                "razorpay_signature": signature,
            },
        )

    def _assert_paid(self):
        self.reg.refresh_from_db()
        self.sub.refresh_from_db()
        self.agent.refresh_from_db()
        self.assertEqual(
            (self.reg.payment_status, self.reg.razorpay_payment_id),
            ("success", PAYMENT),
        )
        self.assertEqual(
            (self.sub.payment_status, self.sub.razorpay_payment_id),
            ("completed", PAYMENT),
        )
        self.assertEqual(self.agent.status, "pending_approval")
        self.assertIsNotNone(self.agent.user)

    def test_webhook_first_then_browser(self, queue, _client):
        self.assertEqual(self._webhook(_payment()).status_code, 200)
        self._assert_paid()
        self.assertEqual(queue.call_count, 1)

        resp = self._browser()
        self.assertTrue(resp.json()["success"], resp.content)
        self.assertEqual(queue.call_count, 1)  # no second invoice / welcome
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.agent.user_id)
        self.assertEqual(
            self.client.session["registration_success_email"], self.agent.email
        )
        self.assertEqual(self.client.get("/events/success/").status_code, 200)

    def test_browser_first_then_webhook_is_idempotent(self, queue, client_factory):
        client_factory.return_value = MagicMock(
            **{"payment.fetch.return_value": _payment()}
        )
        resp = self._browser()
        self.assertTrue(resp.json()["success"], resp.content)
        self._assert_paid()
        self.assertEqual(self._webhook(_payment()).status_code, 200)
        self.assertEqual(queue.call_count, 1)

    def test_amount_mismatch_is_acked_and_not_fulfilled(self, queue, _client):
        self.assertEqual(self._webhook(_payment(amount=100)).status_code, 200)
        self.reg.refresh_from_db()
        self.sub.refresh_from_db()
        self.assertEqual(
            (self.reg.payment_status, self.sub.payment_status), ("pending", "pending")
        )
        queue.assert_not_called()

    def test_uncaptured_payment_is_not_fulfilled(self, queue, _client):
        self.assertEqual(self._webhook(_payment(status="failed")).status_code, 200)
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.payment_status, "pending")
        queue.assert_not_called()

    def test_recover_command_fulfils_orphaned_event_registration(self, queue, _client):
        rzp = MagicMock(**{"payment.all.return_value": {"items": [_payment()]}})
        out = StringIO()
        with patch(
            "apps.agents.services.razorpay_checkout.razorpay_client", return_value=rzp
        ):
            call_command(
                "recover_orphaned_payments", "--days", "7", "--apply", stdout=out
            )
        self.assertIn("EVENT_NOT_FULFILLED", out.getvalue())
        self._assert_paid()
        self.assertEqual(queue.call_count, 1)

    def test_new_order_never_overwrites_another_orders_row(self, _queue, _client):
        from apps.agents.views.events import _link_order_to_subscription

        _link_order_to_subscription(self.agent, "order_EVTNEWER0002")
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.razorpay_order_id, ORDER)
        self.assertTrue(
            AgentSubscription.objects.filter(
                agent=self.agent,
                razorpay_order_id="order_EVTNEWER0002",
                payment_status="pending",
            ).exists()
        )
