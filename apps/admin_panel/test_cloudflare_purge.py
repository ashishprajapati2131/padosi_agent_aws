import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, RequestFactory
from apps.admin_panel.services import cloudflare
from apps.admin_panel.views.system import purge_cloudflare, save_cloudflare_settings
from apps.home.models.site_setting import SiteSetting


class DummyMessages:
    def __init__(self):
        self.messages = []

    def add(self, level, message, extra_tags=""):
        self.messages.append(message)

    def success(self, message):
        self.messages.append(message)

    def error(self, message):
        self.messages.append(message)

    def warning(self, message):
        self.messages.append(message)

    def __iter__(self):
        return iter(self.messages)


class CloudflarePurgeTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        SiteSetting.flush_cache()
        SiteSetting.objects.all().delete()

    def test_cloudflare_not_configured_by_default(self):
        is_cfg = cloudflare.is_configured()
        self.assertFalse(is_cfg)

    def test_cloudflare_save_credentials(self):
        cloudflare.save_credentials("test_zone_123", "test_token_456")
        zone_id, api_token = cloudflare.get_credentials()
        self.assertEqual(zone_id, "test_zone_123")
        self.assertEqual(api_token, "test_token_456")
        self.assertTrue(cloudflare.is_configured())

    @patch("apps.admin_panel.services.cloudflare.urllib.request.urlopen")
    def test_cloudflare_purge_cache_success(self, mock_urlopen):
        cloudflare.save_credentials("zone_abc", "token_xyz")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"success": True, "result": {"id": "123"}}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        success, msg = cloudflare.purge_cache()
        self.assertTrue(success)
        self.assertIn("successfully purged", msg)

    @patch("apps.admin_panel.views.system._get_admin_from_session")
    def test_purge_cloudflare_ajax_requires_setup(self, mock_admin):
        mock_admin.return_value = 1
        req = self.factory.post("/admin/system/purge-cloudflare/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        req._messages = DummyMessages()

        resp = purge_cloudflare(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode("utf-8"))
        self.assertFalse(data["success"])
        self.assertTrue(data.get("requires_setup"))
        self.assertIn("dash_url", data)

    @patch("apps.admin_panel.services.cloudflare.urllib.request.urlopen")
    @patch("apps.admin_panel.views.system._get_admin_from_session")
    def test_purge_cloudflare_ajax_success(self, mock_admin, mock_urlopen):
        mock_admin.return_value = 1
        cloudflare.save_credentials("zone_abc", "token_xyz")

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"success": True}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        req = self.factory.post("/admin/system/purge-cloudflare/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        req._messages = DummyMessages()

        resp = purge_cloudflare(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode("utf-8"))
        self.assertTrue(data["success"])
        self.assertIn("successfully purged", data["message"])

    @patch("apps.admin_panel.views.system._get_admin_from_session")
    def test_save_cloudflare_settings_view(self, mock_admin):
        mock_admin.return_value = 1
        req = self.factory.post(
            "/admin/system/save-cloudflare/",
            data={"cloudflare_zone_id": "new_zone_999", "cloudflare_api_token": "new_token_888"}
        )
        req._messages = DummyMessages()

        resp = save_cloudflare_settings(req)
        self.assertEqual(resp.status_code, 302)
        zone_id, api_token = cloudflare.get_credentials()
        self.assertEqual(zone_id, "new_zone_999")
        self.assertEqual(api_token, "new_token_888")
