"""Hub live diagnostics (webhook trace) and the production gate on the Web Simulator."""

import json
from unittest.mock import patch

from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.wa_agent_bot import simulator_views, views
from apps.wa_agent_bot.services import webhook_trace

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "diag-tests",
    }
}


@override_settings(CACHES=LOCMEM)
class WebhookTraceTests(SimpleTestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def _post(self, body, token=""):
        url = "/wa-bot/webhook/" + (f"?token={token}" if token else "")
        return RequestFactory().post(
            url, data=json.dumps(body), content_type="application/json"
        )

    def test_paused_bot_is_recorded(self):
        with patch.object(views, "is_wa_bot_enabled", return_value=False):
            views.webhook_receiver(
                self._post({"event": "message.received", "data": {}})
            )
        event = webhook_trace.recent()[0]
        self.assertEqual(event["outcome"], webhook_trace.IGNORED)
        self.assertIn("paused", event["detail"])
        self.assertIsNotNone(webhook_trace.last_seen())

    @patch.dict("os.environ", {"WA_BOT_WEBHOOK_SECRET": "s3cret"})
    def test_wrong_token_is_recorded_with_the_fix(self):
        with patch.object(views, "is_wa_bot_enabled", return_value=True):
            response = views.webhook_receiver(
                self._post({"event": "message.received"}, token="nope")
            )
        self.assertEqual(response.status_code, 403)
        self.assertIn("1-Click Sync Webhook", webhook_trace.recent()[0]["detail"])

    @patch.dict("os.environ", {"WA_BOT_WEBHOOK_SECRET": ""})
    @override_settings(DEBUG=False)
    def test_missing_secret_is_named(self):
        with patch.object(views, "is_wa_bot_enabled", return_value=True):
            views.webhook_receiver(self._post({"event": "message.received"}))
        self.assertIn(
            "WA_BOT_WEBHOOK_SECRET is not set", webhook_trace.recent()[0]["detail"]
        )

    @patch.dict("os.environ", {"WA_BOT_WEBHOOK_SECRET": "s3cret"})
    def test_lid_sender_without_phone_names_the_setting(self):
        body = {
            "event": "message.received",
            "data": {"from": "1234567890@lid", "body": "LIAFI"},
        }
        with patch.object(views, "is_wa_bot_enabled", return_value=True):
            views.webhook_receiver(self._post(body, token="s3cret"))
        self.assertIn("RESOLVE_LID_TO_PHONE", webhook_trace.recent()[0]["detail"])

    def test_own_echoes_and_groups_are_not_traced(self):
        self.assertIsNone(
            views._no_phone_reason({"data": {"from": "91999@c.us", "fromMe": True}})
        )
        self.assertIsNone(views._no_phone_reason({"data": {"from": "1203@g.us"}}))

    def test_trace_keeps_the_newest_entries_and_masks_phones(self):
        for i in range(webhook_trace.TRACE_SIZE + 5):
            webhook_trace.record(
                webhook_trace.PROCESSED, f"n{i}", "919876543210", "LIAFI"
            )
        events = webhook_trace.recent()
        self.assertEqual(len(events), webhook_trace.TRACE_SIZE)
        self.assertEqual(events[0]["detail"], f"n{webhook_trace.TRACE_SIZE + 4}")
        self.assertNotIn("9876543210", events[0]["phone"])


@override_settings(DEBUG=False)
class SimulatorProductionGateTests(SimpleTestCase):
    def _request(self):
        return RequestFactory().post("/wa-bot/simulator/simulate-payment/")

    def test_staff_admin_gets_404_in_production(self):
        with (
            patch("apps.admin_panel.auth._get_admin_from_session", return_value=2),
            patch("apps.admin_panel.auth.is_super_admin", return_value=False),
        ):
            with self.assertRaises(Http404):
                simulator_views.simulator_payment(self._request())

    def test_super_admin_may_open_it_but_never_simulate_a_payment(self):
        with (
            patch("apps.admin_panel.auth._get_admin_from_session", return_value=1),
            patch("apps.admin_panel.auth.is_super_admin", return_value=True),
        ):
            response = simulator_views.simulator_payment(self._request())
        self.assertEqual(response.status_code, 403)
        self.assertIn("disabled in production", json.loads(response.content)["message"])


class WebhookFirewallTests(SimpleTestCase):
    """Customer chat text must not let the firewall ban the OpenWA server and silence the bot."""

    def _middleware(self):
        from django.http import HttpResponse

        from apps.admin_panel.middleware.security import ThreatMonitorMiddleware

        return ThreatMonitorMiddleware(lambda request: HttpResponse("reached"))

    def _post(self, path):
        body = {"event": "message.received", "data": {"from": "91999@c.us", "body": "javascript: ../../ x"}}
        request = RequestFactory().post(path, data=json.dumps(body), content_type="application/json")
        request.META["REMOTE_ADDR"] = "203.0.113.7"
        return request

    def test_webhook_skips_ip_ban_and_content_scan(self):
        with patch("apps.admin_panel.middleware.security.is_ip_blocked", return_value=True):
            response = self._middleware()(self._post("/wa-bot/webhook/"))
        self.assertEqual(response.content, b"reached")

    def test_other_paths_stay_protected(self):
        with patch("apps.admin_panel.middleware.security.is_ip_blocked", return_value=True):
            response = self._middleware()(self._post("/contact/"))
        self.assertEqual(response.status_code, 403)


class _Resp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


HOOK = "https://padosiagent.com/wa-bot/webhook/"


@override_settings(CACHES=LOCMEM)
@patch.dict("os.environ", {"WA_BOT_WEBHOOK_SECRET": "s3cret"})
class WebhookSyncAndPipelineTests(SimpleTestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        from apps.wa_agent_bot.services import openwa_admin_service as svc

        self.svc = svc
        cfg = patch.object(svc, "get_openwa_config", return_value={"base_url": "https://wa.example", "session_id": "S1", "api_key": "k"})
        cfg.start()
        self.addCleanup(cfg.stop)

    def test_sync_repairs_stale_webhook_and_deletes_duplicates_only_of_ours(self):
        existing = [
            {"id": "a", "url": HOOK, "active": True, "events": ["message.received"]},  # no token
            {"id": "b", "url": HOOK + "?token=old", "active": True, "events": ["*"]},
            {"id": "c", "url": "https://other.example/hook", "active": True, "events": ["*"]},
        ]
        with patch.object(self.svc.requests, "get", return_value=_Resp(200, existing)), patch.object(
            self.svc.requests, "delete", return_value=_Resp(204)
        ) as delete, patch.object(self.svc.requests, "patch", return_value=_Resp(200, {})) as patch_call:
            ok, message, webhook_id = self.svc.sync_openwa_webhook(HOOK)
        self.assertTrue(ok)
        self.assertEqual(webhook_id, "a")
        self.assertEqual([c.args[0].rsplit("/", 1)[1] for c in delete.call_args_list], ["b"])
        self.assertEqual(patch_call.call_args.kwargs["json"]["url"], HOOK + "?token=s3cret")
        self.assertIn("Removed 1 duplicate", message)

    def _run(self, test_result, arrived, reason=""):
        def fake_post(url, **kw):
            if arrived:
                webhook_trace.seen("test")
                if reason:
                    webhook_trace.record(webhook_trace.REJECTED, reason)
            return _Resp(200, test_result)

        status = {"online": True, "is_connected": True, "phone": "919000000001", "latency_ms": 5, "status": "ready"}
        with patch("apps.wa_agent_bot.views.is_wa_bot_enabled", return_value=True), patch.object(
            self.svc, "get_openwa_session_status", return_value=status
        ), patch.object(self.svc, "sync_openwa_webhook", return_value=(True, "ok", "w1")), patch.object(
            self.svc.requests, "post", side_effect=fake_post
        ):
            return self.svc.run_pipeline_test(HOOK)

    def test_all_green_names_the_bot_number(self):
        result = self._run({"success": True, "statusCode": 200}, arrived=True)
        self.assertTrue(result["ok"])
        self.assertIn("+919000000001", result["verdict"])

    def test_403_that_never_arrived_blames_cloudflare(self):
        result = self._run({"success": False, "statusCode": 403}, arrived=False)
        self.assertFalse(result["ok"])
        self.assertIn("Cloudflare", result["verdict"])

    def test_403_that_arrived_reports_our_own_reason(self):
        result = self._run({"success": False, "statusCode": 403}, arrived=True, reason="Wrong or missing webhook token")
        self.assertIn("Wrong or missing webhook token", result["verdict"])

    def test_stops_early_when_bot_is_off(self):
        with patch("apps.wa_agent_bot.views.is_wa_bot_enabled", return_value=False):
            result = self.svc.run_pipeline_test(HOOK)
        self.assertEqual(len(result["steps"]), 1)
        self.assertIn("Turn the bot ON", result["verdict"])
