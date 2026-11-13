"""Phase-3 quick audit fixes: WA6, WA10, WA15, WA17."""

import json
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.agents.models import Agent
from apps.wa_agent_bot import simulator_views, views
from apps.wa_agent_bot.models import WaBotSession
from apps.wa_agent_bot.services.state_machine import process_message
from apps.wa_agent_bot.test_payment_hardening import SECRET, _event, _signed_post


@patch("apps.agents.services.razorpay_checkout.razorpay_client", return_value=None)
@patch(
    "apps.agents.services.razorpay_checkout.razorpay_webhook_secret",
    return_value=SECRET,
)
@patch(
    "apps.wa_agent_bot.services.payment_service.activate_agent_subscription_after_payment"
)
@patch("apps.agents.models.AgentSubscription.objects")
class WebhookRetryAfterFailureTests(SimpleTestCase):
    """WA6: a failed activation must not make the retry look like a duplicate."""

    def _post(self):
        req = _signed_post(_event("payment.captured"))
        req.META["HTTP_X_RAZORPAY_EVENT_ID"] = "evt_wa6"
        return views.razorpay_webhook(req)

    def test_failed_activation_is_retryable_and_success_dedups(
        self, objects, activate, *_
    ):
        cache.delete("rzp_event_evt_wa6")
        objects.filter.return_value.first.return_value = MagicMock(
            id=7, payment_status="pending", registration_amount=1179
        )
        activate.return_value = (False, "boom")
        self._post()
        activate.return_value = (True, "Activated successfully")
        self.assertEqual(json.loads(self._post().content)["status"], "success")
        self.assertEqual(
            json.loads(self._post().content)["message"], "Already processed"
        )
        self.assertEqual(activate.call_count, 2)


class ExtractMessageChatIdTests(SimpleTestCase):
    """WA10: group/@lid/broadcast chat ids are not phone numbers."""

    def test_non_personal_chats_ignored(self):
        for chat in (
            "120363012345678901@g.us",
            "123456789012345@lid",
            "status@broadcast",
        ):
            payload = {"data": {"from": chat, "body": "hi"}}
            self.assertEqual(views._extract_message_data(payload)[0], None, chat)

    def test_personal_chats_accepted(self):
        for chat in ("919876543210@c.us", "919876543210@s.whatsapp.net"):
            payload = {"data": {"from": chat, "body": "hi"}}
            self.assertEqual(views._extract_message_data(payload)[0], "919876543210")


class SimulatorProductionTests(SimpleTestCase):
    """WA15: simulator endpoints do not exist outside DEBUG."""

    @override_settings(DEBUG=False)
    def test_simulator_404_in_production(self):
        req = RequestFactory().get("/wa-bot/simulator/")
        for view in (
            simulator_views.simulator_page,
            simulator_views.simulator_send,
            simulator_views.simulator_reset,
            simulator_views.simulator_payment,
            simulator_views.simulator_toggle,
            simulator_views.simulator_poll,
        ):
            with self.assertRaises(Http404):
                view(req)


class TakenContactMessageTests(TestCase):
    """WA17: the bot must not confirm which email/mobile is registered."""

    def test_taken_email_reply_is_generic_and_state_kept(self):
        Agent.objects.create(
            fullname="X", email="taken@example.com", mobile="9000000009"
        )
        session = WaBotSession.objects.create(
            phone_number="919876500077",
            state=WaBotSession.STATE_ASK_EMAIL,
            registration_data={},
        )
        reply = process_message(session, "taken@example.com")
        self.assertIn("can't be used here", reply)
        self.assertNotIn("taken@example.com", reply)
        self.assertNotIn("already exists", reply)
        self.assertEqual(session.state, WaBotSession.STATE_ASK_EMAIL)
