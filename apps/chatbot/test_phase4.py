"""Phase-4 audit fixes: WA11 (per-session chat cap, 80% warning), WA12 (LLM total deadline)."""

import json
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.chatbot import llm_client, views
from apps.chatbot.test_spend_caps import LOCMEM, _stream


class _Session(dict):
    def __init__(self, key):
        super().__init__()
        self.session_key = key


@override_settings(CACHES=LOCMEM)
class ChatSessionCapTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def _post(self, ip, session):
        req = RequestFactory().post(
            "/chatbot-api/message/",
            json.dumps({"message": "hello"}),
            content_type="application/json",
            REMOTE_ADDR=ip,
            HTTP_ORIGIN="http://testserver",
        )
        req.session = session
        resp = views.send_message(req)
        return (
            b"".join(resp.streaming_content).decode()
            if resp.streaming
            else resp.content.decode()
        )

    @patch.object(views, "CHATBOT_DAILY_SESSION_LIMIT", 2)
    @patch.object(views, "stream_plain_text_completion", side_effect=_stream)
    def test_session_cap_across_ips(self, llm):
        s = _Session("sess-a")
        self._post("198.51.100.30", s)
        self._post("198.51.100.31", s)
        self.assertIn(views.CHAT_IP_LIMIT_REPLY, self._post("198.51.100.32", s))
        self.assertEqual(llm.call_count, 2)
        self.assertNotIn(
            views.CHAT_IP_LIMIT_REPLY, self._post("198.51.100.33", _Session("sess-b"))
        )

    @patch.object(views, "CHATBOT_DAILY_GLOBAL_LIMIT", 5)
    @patch.object(views, "stream_plain_text_completion", side_effect=_stream)
    def test_global_80_percent_warns_once(self, llm):
        with patch.object(views.logger, "warning") as warn:
            for n in range(5):
                self._post(f"198.51.100.{40 + n}", _Session(f"s{n}"))
        self.assertEqual(llm.call_count, 5)  # caps unchanged: all 5 still answered
        self.assertEqual(warn.call_count, 1)
        self.assertIn("80%%", warn.call_args[0][0])


class LlmTotalDeadlineTests(SimpleTestCase):
    PROVIDERS = [
        {"name": "p1", "type": "groq", "api_key_env": "P4_KEY_1", "model": "m"},
        {"name": "p2", "type": "groq", "api_key_env": "P4_KEY_2", "model": "m"},
    ]

    @patch.dict("os.environ", {"P4_KEY_1": "k", "P4_KEY_2": "k"})
    def test_stops_after_deadline(self):
        def _slow_fail(*_a, **_k):
            clock[0] += 30  # first provider eats the whole budget
            raise RuntimeError("timeout")

        clock = [1000.0]
        client = MagicMock()
        client.chat.completions.with_raw_response.create.side_effect = _slow_fail
        with (
            patch.object(
                llm_client, "get_rotated_providers", return_value=self.PROVIDERS
            ),
            patch.object(llm_client, "_get_client", return_value=client) as get_client,
            patch.object(llm_client.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(llm_client.cache, "get", return_value=None),
            patch.object(llm_client.cache, "set"),
        ):
            with self.assertRaises(Exception):
                llm_client.call_llm_with_fallback([{"role": "user", "content": "x"}])
        self.assertEqual(get_client.call_count, 1)  # second provider never tried

    @patch.dict("os.environ", {"P4_KEY_1": "k", "P4_KEY_2": "k"})
    def test_both_tried_within_deadline(self):
        client = MagicMock()
        client.chat.completions.with_raw_response.create.side_effect = RuntimeError(
            "down"
        )
        with (
            patch.object(
                llm_client, "get_rotated_providers", return_value=self.PROVIDERS
            ),
            patch.object(llm_client, "_get_client", return_value=client) as get_client,
            patch.object(llm_client.cache, "get", return_value=None),
            patch.object(llm_client.cache, "set"),
        ):
            with self.assertRaises(Exception):
                llm_client.call_llm_with_fallback(
                    [{"role": "user", "content": "x"}], total_deadline=60
                )
        self.assertEqual(get_client.call_count, 2)
