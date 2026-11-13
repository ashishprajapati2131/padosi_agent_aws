"""WhatsApp-bot Razorpay webhook / activation / inbound dedup hardening."""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.wa_agent_bot import views

SECRET = "whsec_test"


def _signed_post(payload):
    body = json.dumps(payload)
    return RequestFactory().post(
        "/wa-bot/razorpay-webhook/",
        data=body,
        content_type="application/json",
        HTTP_X_RAZORPAY_SIGNATURE=hmac.new(
            SECRET.encode(), body.encode(), hashlib.sha256
        ).hexdigest(),
    )


def _event(event, status="captured", amount=117900):
    return {
        "event": event,
        "payload": {
            "payment_link": {
                "entity": {"id": "plink_1", "notes": {"subscription_id": 7}}
            },
            "payment": {"entity": {"id": "pay_1", "status": status, "amount": amount}},
        },
    }


@patch("apps.agents.services.razorpay_checkout.razorpay_client", return_value=None)
@patch(
    "apps.agents.services.razorpay_checkout.razorpay_webhook_secret",
    return_value=SECRET,
)
@patch(
    "apps.wa_agent_bot.services.payment_service.activate_agent_subscription_after_payment",
    return_value=(True, "Activated successfully"),
)
@patch("apps.agents.models.AgentSubscription.objects")
class WaRazorpayWebhookTests(SimpleTestCase):
    def _sub(self, objects):
        sub = MagicMock(id=7, payment_status="pending", registration_amount=1179)
        objects.filter.return_value.first.return_value = sub
        return sub

    def test_non_paid_events_are_acked_and_ignored(self, objects, activate, *_):
        self._sub(objects)
        for event in (
            "payment_link.expired",
            "payment_link.cancelled",
            "refund.processed",
            "payment.failed",
        ):
            response = views.razorpay_webhook(_signed_post(_event(event)))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(json.loads(response.content)["status"], "ignored")
        activate.assert_not_called()

    def test_paid_event_with_matching_amount_activates(self, objects, activate, *_):
        self._sub(objects)
        response = views.razorpay_webhook(_signed_post(_event("payment.captured")))
        self.assertEqual(json.loads(response.content)["status"], "success")
        activate.assert_called_once()

    def test_amount_mismatch_is_acked_without_activation(self, objects, activate, *_):
        self._sub(objects)
        response = views.razorpay_webhook(
            _signed_post(_event("payment_link.paid", amount=100))
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["message"], "Amount mismatch")
        activate.assert_not_called()

    def test_uncaptured_payment_does_not_activate(self, objects, activate, *_):
        self._sub(objects)
        response = views.razorpay_webhook(
            _signed_post(_event("order.paid", status="failed"))
        )
        self.assertEqual(response.status_code, 200)
        activate.assert_not_called()


class WaInboundDedupTests(SimpleTestCase):
    def test_redelivered_message_is_processed_once(self):
        cache.delete("wa_bot_msg_false_919800000001@c.us_ABC")
        payload = {
            "event": "message:received",
            "data": {
                "from": "919800000001@c.us",
                "body": "hi",
                "id": {"_serialized": "false_919800000001@c.us_ABC"},
            },
        }
        session = MagicMock(state="welcome")
        with (
            patch.object(views, "is_wa_bot_enabled", return_value=True),
            patch.object(views, "_verify_webhook_signature", return_value=True),
            patch.object(views, "_check_rate_limit", return_value=True),
            patch.object(
                views.WaBotSession.objects,
                "get_or_create",
                return_value=(session, False),
            ),
            patch.object(views.WaBotMessageLog.objects, "create"),
            patch.object(views, "send_text_message", return_value={"success": True}),
            patch.object(views, "process_message", return_value="ok") as process,
        ):
            for _ in range(2):
                request = RequestFactory().post(
                    "/wa-bot/webhook/",
                    data=json.dumps(payload),
                    content_type="application/json",
                )
                views.webhook_receiver(request)
        process.assert_called_once()


@patch(
    "apps.wa_agent_bot.services.payment_service.send_text_message",
    return_value={"success": True},
)
@patch("apps.wa_agent_bot.services.payment_service.queue_invoice_and_welcome")
class WaActivationStatusTests(TestCase):
    def _sub(self, status):
        from apps.agents.models import Agent, AgentSubscription

        agent = Agent.objects.create(
            fullname="Bot Agent",
            email=f"bot.{status}@example.com",
            mobile="9800000077",
            status=status,
            plan_type="starter",
        )
        return AgentSubscription.objects.create(
            agent=agent,
            selected_plan="Starter",
            registration_amount=1179,
            payment_status="pending",
            status="inactive",
        )

    def test_active_agent_is_not_demoted(self, *_):
        from apps.wa_agent_bot.services.payment_service import (
            activate_agent_subscription_after_payment,
        )

        sub = self._sub("active")
        ok, _msg = activate_agent_subscription_after_payment(sub.id, payment_id="pay_x")
        self.assertTrue(ok)
        sub.agent.refresh_from_db()
        self.assertEqual(sub.agent.status, "active")

    def test_new_agent_goes_to_approval_and_second_call_is_noop(self, queue, _send):
        from apps.wa_agent_bot.services.payment_service import (
            activate_agent_subscription_after_payment,
        )

        sub = self._sub("pending_payment")
        activate_agent_subscription_after_payment(sub.id, payment_id="pay_y")
        sub.agent.refresh_from_db()
        self.assertEqual(sub.agent.status, "pending_approval")
        self.assertEqual(
            activate_agent_subscription_after_payment(sub.id, payment_id="pay_y"),
            (True, "Already activated"),
        )
        self.assertEqual(queue.call_count, 1)

    def test_whatsapp_send_waits_for_commit(self, _queue, send):  # audit WA5
        from apps.wa_agent_bot.services.payment_service import (
            activate_agent_subscription_after_payment,
        )

        sub = self._sub("pending_payment")
        with self.captureOnCommitCallbacks() as callbacks:
            activate_agent_subscription_after_payment(sub.id, payment_id="pay_z")
            send.assert_not_called()
        self.assertEqual(len(callbacks), 1)
        callbacks[0]()
        send.assert_called()


class PaymentLinkPaidInFullTests(SimpleTestCase):
    """Audit WA4: 'paid' alone is not enough; the amount must be what we priced."""

    def _check(self, link):
        from unittest.mock import MagicMock

        from apps.wa_agent_bot.services.payment_service import payment_link_paid_in_full

        return payment_link_paid_in_full(link, MagicMock(registration_amount=1179))

    def test_paid_with_right_amount(self):
        self.assertTrue(self._check({"status": "paid", "amount_paid": 117900}))

    def test_rejects_wrong_amount_unpaid_and_empty(self):
        self.assertFalse(self._check({"status": "paid", "amount_paid": 100}))
        self.assertFalse(self._check({"status": "paid"}))
        self.assertFalse(self._check({"status": "created", "amount_paid": 117900}))
        self.assertFalse(self._check(None))
