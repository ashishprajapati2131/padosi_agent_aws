"""Phase-4 audit fixes: WA3 (temp password cleanup), WA7 (session lock), WA13, WA14, WA16."""

import json
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.agents.models import Agent, AgentSubscription
from apps.wa_agent_bot import views
from apps.wa_agent_bot.models import WaBotMessageLog, WaBotSession
from apps.wa_agent_bot.services import broadcast, payment_service
from apps.wa_agent_bot.services.message_sender import mask_email, mask_phone
from apps.wa_agent_bot.services.state_machine import process_message
from apps.wa_agent_bot.test_payment_hardening import SECRET, _event, _signed_post


def _agent(email="p4.agent@example.com", status="pending_payment"):
    return Agent.objects.create(
        fullname="Phase Four",
        email=email,
        mobile="9800000044",
        status=status,
        plan_type="starter",
    )


def _sub(agent, order_id="", status="pending"):
    return AgentSubscription.objects.create(
        agent=agent,
        selected_plan="Starter",
        registration_amount=1179,
        payment_status=status,
        status="inactive",
        razorpay_order_id=order_id,
    )


@patch("apps.wa_agent_bot.services.payment_service.queue_invoice_and_welcome")
class TempPasswordCleanupTests(TestCase):
    """WA3: the plaintext temp password is dropped once the welcome message is delivered."""

    def _activate(self, send_ok):
        agent = _agent()
        sub = _sub(agent, "plink_wa3")
        session = WaBotSession.objects.create(
            phone_number="919800000044",
            agent=agent,
            state=WaBotSession.STATE_AWAITING_PAYMENT,
            registration_data={"temp_password": "Tmp-pass-123"},
        )
        with (
            patch.object(
                payment_service, "send_text_message", return_value={"success": send_ok}
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            payment_service.activate_agent_subscription_after_payment(sub.id, "pay_wa3")
        session.refresh_from_db()
        return session

    def test_cleared_after_successful_delivery(self, _queue):
        session = self._activate(send_ok=True)
        self.assertEqual(session.generated_password, "")
        self.assertNotIn("temp_password", session.registration_data)
        self.assertTrue(session.is_logged_in)

    def test_kept_until_retry_then_cleared(self, _queue):
        session = self._activate(send_ok=False)
        self.assertEqual(session.generated_password, "Tmp-pass-123")
        self.assertTrue(session.registration_data["pending_credentials_delivery"])

        reply = process_message(session, "hi")
        self.assertIn("Login", reply)
        session.refresh_from_db()
        self.assertEqual(session.generated_password, "")
        self.assertNotIn("temp_password", session.registration_data)
        self.assertNotIn("pending_credentials_delivery", session.registration_data)


class WebhookSessionLockTests(TestCase):
    """WA7: the webhook works on a freshly locked row, not the copy loaded before the lock."""

    def test_concurrent_activation_is_not_overwritten(self):
        agent = _agent()
        WaBotSession.objects.create(
            phone_number="919800000045",
            agent=agent,
            state=WaBotSession.STATE_LOGGED_IN,
            is_logged_in=True,
            is_registered=True,
        )
        # Copy loaded before a payment activation committed.
        stale = WaBotSession.objects.get(phone_number="919800000045")
        stale.state = WaBotSession.STATE_AWAITING_PAYMENT
        stale.is_logged_in = stale.is_registered = False

        seen = {}

        def _process(session, text):
            seen["state"] = session.state
            return "ok"

        payload = {
            "event": "message:received",
            "data": {"from": "919800000045@c.us", "body": "hi"},
        }
        with (
            patch.object(views, "is_wa_bot_enabled", return_value=True),
            patch.object(views, "_verify_webhook_signature", return_value=True),
            patch.object(views, "_check_rate_limit", return_value=True),
            patch.object(
                views.WaBotSession.objects, "get_or_create", return_value=(stale, False)
            ),
            patch.object(views, "send_text_message", return_value={"success": True}),
            patch.object(views, "process_message", side_effect=_process),
        ):
            views.webhook_receiver(
                RequestFactory().post(
                    "/wa-bot/webhook/",
                    data=json.dumps(payload),
                    content_type="application/json",
                )
            )
        self.assertEqual(seen["state"], WaBotSession.STATE_LOGGED_IN)
        row = WaBotSession.objects.get(phone_number="919800000045")
        self.assertTrue(row.is_logged_in)
        self.assertEqual(row.state, WaBotSession.STATE_LOGGED_IN)


class BroadcastAlreadySentTests(TestCase):
    """WA13: dedup matches the exact stored number, not any number ending in the same digits."""

    def _log(self, phone):
        WaBotMessageLog.objects.create(
            phone_number=phone,
            direction=WaBotMessageLog.DIRECTION_OUT,
            category=broadcast.CATEGORY,
            status=WaBotMessageLog.STATUS_SENT,
            content="Hello",
        )

    def test_exact_match_only(self):
        self._log("449876543210")  # different number sharing the last 10 digits
        self.assertFalse(broadcast.already_sent("9876543210", "Hello"))
        self._log("9876543210")
        self.assertTrue(broadcast.already_sent("9876543210", "Hello"))

    def test_country_code_form_matches(self):
        self._log("919876543211")
        self.assertTrue(broadcast.already_sent("9876543211", "Hello"))


@patch("apps.wa_agent_bot.services.payment_service.queue_invoice_and_welcome")
@patch(
    "apps.wa_agent_bot.services.payment_service.send_text_message",
    return_value={"success": True},
)
class SupersededPaymentLinkTests(TestCase):
    """WA14: a new plan link supersedes old unpaid ones, but a late payment on an old link still activates."""

    def test_old_link_marked_failed_and_cancelled_but_still_activates(self, *_):
        agent = _agent()
        old = _sub(agent, "plink_old")
        website = _sub(agent, "order_web")  # website checkout rows are left alone
        session = WaBotSession.objects.create(
            phone_number="919800000044",
            agent=agent,
            registration_data={"fullname": "Phase Four"},
        )
        client = MagicMock()
        client.payment_link.create.return_value = {
            "id": "plink_new",
            "short_url": "https://rzp.io/x",
        }
        with (
            patch.object(payment_service, "razorpay_client", return_value=client),
            patch.object(
                payment_service,
                "create_or_update_pending_agent",
                return_value=(agent, None, "Tmp-pass-123"),
            ),
        ):
            info = payment_service.create_plan_payment_link(session, "starter")

        self.assertTrue(info["success"])
        client.payment_link.cancel.assert_called_once_with("plink_old")
        old.refresh_from_db()
        website.refresh_from_db()
        self.assertEqual(
            (old.payment_status, old.razorpay_order_id), ("failed", "plink_old")
        )
        self.assertEqual(website.payment_status, "pending")
        self.assertEqual(info["subscription"].payment_status, "pending")

        # The customer pays the old link anyway: the webhook still finds and activates it.
        cache.delete("rzp_event_evt_wa14")
        event = _event("payment_link.paid")
        event["payload"]["payment_link"]["entity"] = {
            "id": "plink_old",
            "notes": {"subscription_id": old.id},
        }
        with (
            patch(
                "apps.agents.services.razorpay_checkout.razorpay_webhook_secret",
                return_value=SECRET,
            ),
            patch(
                "apps.agents.services.razorpay_checkout.razorpay_client",
                return_value=None,
            ),
        ):
            response = views.razorpay_webhook(_signed_post(event))
        self.assertEqual(json.loads(response.content)["status"], "success")
        old.refresh_from_db()
        self.assertEqual(old.payment_status, "completed")

    def test_cancel_failure_is_best_effort(self, *_):
        agent = _agent()
        old = _sub(agent, "plink_paid")
        session = WaBotSession.objects.create(
            phone_number="919800000044", agent=agent, registration_data={}
        )
        client = MagicMock()
        client.payment_link.cancel.side_effect = Exception("already paid")
        client.payment_link.create.return_value = {
            "id": "plink_new2",
            "short_url": "https://rzp.io/y",
        }
        with (
            patch.object(payment_service, "razorpay_client", return_value=client),
            patch.object(
                payment_service,
                "create_or_update_pending_agent",
                return_value=(agent, None, "Tmp-pass-123"),
            ),
        ):
            self.assertTrue(
                payment_service.create_plan_payment_link(session, "starter")["success"]
            )
        old.refresh_from_db()
        self.assertEqual(old.razorpay_order_id, "plink_paid")


class LogMaskingTests(SimpleTestCase):
    """WA16: phone numbers and emails in log lines are masked."""

    def test_masks(self):
        self.assertEqual(mask_phone("919876543210"), "******3210")
        self.assertEqual(mask_phone(""), "")
        self.assertEqual(mask_email("abcdef@example.com"), "ab***@example.com")
        self.assertEqual(mask_email("not-an-email"), "***")

    def test_sender_log_has_no_full_number(self):
        from apps.wa_agent_bot.services import message_sender

        response = MagicMock(status_code=200, text="")
        with (
            patch.object(
                message_sender,
                "_get_config",
                return_value={
                    "base_url": "http://x",
                    "session_id": "s",
                    "api_key": "k",
                },
            ),
            patch.object(message_sender.requests, "post", return_value=response),
            self.assertLogs(message_sender.logger, "INFO") as logs,
        ):
            message_sender._send("919876543210", "hi")
        self.assertNotIn("919876543210", "\n".join(logs.output))
        self.assertIn("******3210", "\n".join(logs.output))
