"""LLM spend caps: chatbot daily per-IP / global limits, origin check, bio per-agent cap."""

import json
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.chatbot import views

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "spend-caps",
    }
}


def _stream(*_args, **_kwargs):
    yield {"type": "chunk", "delta": "hi"}
    yield {"type": "done", "reply": "hi"}


@override_settings(CACHES=LOCMEM)
class ChatbotSpendCapTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def _post(self, ip="198.51.100.10", **headers):
        headers.setdefault("HTTP_ORIGIN", "http://testserver")
        req = RequestFactory().post(
            "/chatbot-api/message/",
            json.dumps({"message": "hello"}),
            content_type="application/json",
            REMOTE_ADDR=ip,
            **headers,
        )
        req.session = {}
        resp = views.send_message(req)
        body = (
            b"".join(resp.streaming_content).decode()
            if resp.streaming
            else resp.content.decode()
        )
        return resp.status_code, body

    @patch.object(views, "CHATBOT_DAILY_IP_LIMIT", 2)
    @patch.object(views, "stream_plain_text_completion", side_effect=_stream)
    def test_ip_daily_cap_replies_without_llm(self, llm):
        self._post()
        self._post()
        status, body = self._post()
        self.assertEqual(status, 200)
        self.assertIn(views.CHAT_IP_LIMIT_REPLY, body)
        self.assertEqual(llm.call_count, 2)
        self.assertNotIn(
            views.CHAT_IP_LIMIT_REPLY, self._post(ip="198.51.100.11")[1]
        )  # other IPs unaffected

    @patch.object(views, "CHATBOT_DAILY_GLOBAL_LIMIT", 1)
    @patch.object(views, "stream_plain_text_completion", side_effect=_stream)
    def test_global_ceiling_replies_without_llm_and_alerts_once(self, llm):
        self._post(ip="198.51.100.20")
        with patch.object(views.logger, "error") as alert:
            for n in range(21, 24):
                status, body = self._post(ip=f"198.51.100.{n}")
                self.assertEqual(status, 200)
                self.assertIn(views.CHAT_UNAVAILABLE_REPLY, body)
        self.assertEqual(llm.call_count, 1)
        self.assertEqual(alert.call_count, 1)

    @patch.object(views, "stream_plain_text_completion", side_effect=_stream)
    def test_origin_or_referer_required(self, llm):
        self.assertEqual(self._post(HTTP_ORIGIN="")[0], 403)
        self.assertEqual(self._post(HTTP_ORIGIN="https://evil.example")[0], 403)
        self.assertEqual(
            self._post(HTTP_ORIGIN="", HTTP_REFERER="https://evil.example/x")[0], 403
        )
        self.assertEqual(
            self._post(HTTP_ORIGIN="", HTTP_REFERER="http://testserver/find-agents/")[
                0
            ],
            200,
        )
        self.assertEqual(self._post()[0], 200)


@override_settings(CACHES=LOCMEM)
class BioDailyCapTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_agent_cap_stops_llm_calls(self):
        from apps.agents.views import bio_generator as bg

        agent = MagicMock(pk=7, fullname="Asha")
        with (
            patch.object(bg, "BIO_DAILY_AGENT_LIMIT", 1),
            patch.object(bg, "AgentBioGenerationLog"),
            patch.object(
                bg,
                "_generate_bio_with_retries",
                return_value=("I help families.", "", None, "x"),
            ) as llm,
        ):
            self.assertEqual(
                bg.generate_agent_bio_logic(agent, MagicMock(), {}), "I help families."
            )
            with self.assertRaises(bg.BioDailyLimitExceeded):
                bg.generate_agent_bio_logic(agent, MagicMock(), {})
        self.assertEqual(llm.call_count, 1)
