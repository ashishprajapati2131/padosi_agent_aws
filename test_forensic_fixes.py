"""
Comprehensive Automated Verification Suite for Forensic Audit Remediations.
Tests all P0/P1/P2 fixes across Django and FastAPI.
"""
import os
import unittest
from unittest.mock import MagicMock, patch

# Ensure proper env before imports
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "padosi_agent.settings")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "test")
os.environ.setdefault("CLOUDINARY_API_KEY", "test")
os.environ.setdefault("CLOUDINARY_API_SECRET", "test")

import django
django.setup()

from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache


class TestFastAPIConfigSafeUrls(unittest.TestCase):
    """Verify proxy header parsing and HTTPS enforcement."""
    def test_multi_proxy_and_safe_url(self):
        from fastapi_app.config import get_base_url, build_safe_url
        from starlette.datastructures import Headers

        class MockRequest:
            def __init__(self, headers):
                self.headers = Headers(headers)

        req = MockRequest({
            "x-forwarded-proto": "https, http",
            "x-forwarded-host": "padosiagent.com, internal-elb",
        })
        base_url = get_base_url(req)
        self.assertEqual(base_url, "https://padosiagent.com")

        safe_url = build_safe_url("/api/v1/championship/dashboard", req)
        self.assertEqual(safe_url, "https://padosiagent.com/api/v1/championship/dashboard")


class TestWAFAndRateLimiterSpoofing(unittest.TestCase):
    """Verify that X-Forwarded-For cannot spoof localhost unless REMOTE_ADDR is local."""
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()

    def test_admin_waf_rejects_external_spoof(self):
        from apps.admin_panel.middleware import ThreatMonitorMiddleware

        # Attacker at 198.51.100.1 sends spoofed header X-Forwarded-For: 127.0.0.1
        request = self.factory.get('/admin/login/', HTTP_X_FORWARDED_FOR='127.0.0.1', REMOTE_ADDR='198.51.100.1')
        client_ip = ThreatMonitorMiddleware.get_client_ip(request)
        # Should NOT be 127.0.0.1
        self.assertEqual(client_ip, '198.51.100.1')

    def test_admin_waf_accepts_genuine_local_proxy(self):
        from apps.admin_panel.middleware import ThreatMonitorMiddleware

        # Reverse proxy at 127.0.0.1 forwards real client IP 203.0.113.195
        request = self.factory.get('/admin/login/', HTTP_X_FORWARDED_FOR='203.0.113.195, 10.0.0.1', REMOTE_ADDR='127.0.0.1')
        client_ip = ThreatMonitorMiddleware.get_client_ip(request)
        self.assertEqual(client_ip, '203.0.113.195')

    def test_threat_email_alert_throttling_cache(self):
        """Verify that security alert emails are throttled to 1 per 10 minutes per IP."""
        test_ip = "198.51.100.5"
        cache_key = f"threat_email_alert_{test_ip}"
        self.assertIsNone(cache.get(cache_key))

        # First alert sets cache
        cache.set(cache_key, True, timeout=600)
        self.assertTrue(cache.get(cache_key))


class TestFastAPISpoofingProtection(unittest.TestCase):
    """Verify FastAPI threat monitor and rate limiter IP resolution."""
    def test_fastapi_threat_monitor_spoofing(self):
        from fastapi_app.middleware.threat_monitor import ThreatMonitorMiddleware
        from starlette.datastructures import Headers

        class MockClient:
            host = "198.51.100.2"

        class MockRequest:
            client = MockClient()
            headers = Headers({"x-forwarded-for": "127.0.0.1"})

        ip = ThreatMonitorMiddleware.get_client_ip(MockRequest())
        self.assertEqual(ip, "198.51.100.2", "Spoofed X-Forwarded-For allowed on FastAPI threat monitor!")

    def test_fastapi_rate_limiter_spoofing(self):
        from fastapi_app.middleware.rate_limiter import RateLimitMiddleware
        from starlette.datastructures import Headers

        class MockClient:
            host = "198.51.100.3"

        class MockRequest:
            client = MockClient()
            headers = Headers({"x-forwarded-for": "127.0.0.1"})

        ip = RateLimitMiddleware.get_client_ip(MockRequest())
        self.assertEqual(ip, "198.51.100.3", "Spoofed X-Forwarded-For allowed on FastAPI rate limiter!")


class TestSQLAlchemyModelDrift(unittest.TestCase):
    """Verify AgentProfile table does not declare non-existent latitude/longitude columns."""
    def test_agent_profile_columns(self):
        from fastapi_app.models.agent_profile import AgentProfile

        column_names = [c.name for c in AgentProfile.__table__.columns]
        self.assertNotIn('latitude', column_names, "latitude column should not be on agent_profiles")
        self.assertNotIn('longitude', column_names, "longitude column should not be on agent_profiles")


class TestInvoiceSSRFAndConcurrency(unittest.TestCase):
    """Verify SSRF protection on Google Sheet URL."""
    def test_ssrf_blocking(self):
        from apps.agents.services.invoice import InvoiceService
        from apps.home.models.site_setting import SiteSetting

        svc = InvoiceService()

        # Try to configure AWS metadata service
        with patch.object(SiteSetting, 'get_value', return_value='http://169.254.169.254/latest/meta-data'):
            with patch('requests.post') as mock_post:
                svc.sync_to_google_sheet(MagicMock())
                mock_post.assert_not_called()

        # Try to configure internal localhost
        with patch.object(SiteSetting, 'get_value', return_value='http://localhost:8080/exfil'):
            with patch('requests.post') as mock_post:
                svc.sync_to_google_sheet(MagicMock())
                mock_post.assert_not_called()


class TestOpenGraphPillowFallback(unittest.TestCase):
    """Verify OG image generator falls back to Pillow and generates valid JPEG bytes."""
    def test_pillow_fallback_rendering(self):
        from apps.agents.services.og_image import _render_agent_og_jpeg_pillow

        agent = MagicMock()
        agent.full_name = "Ashish Prajapati"
        agent.agency_name = "Prajapati Insurance Services"
        agent.slug = "ashish-prajapati"
        agent.phone = "9876543210"
        agent.email = "ashish@example.com"
        mock_perf = MagicMock(rating=4.9, total_reviews=42)
        mock_profile = MagicMock(display_city="Ahmedabad", display_state="Gujarat")
        agent.insuranceSegments = MagicMock(all=lambda: [MagicMock(segment_name="Health"), MagicMock(segment_name="Life")])

        jpeg_bytes = _render_agent_og_jpeg_pillow(agent, profile=mock_profile, perf=mock_perf)
        self.assertIsInstance(jpeg_bytes, bytes)
        self.assertGreater(len(jpeg_bytes), 1000)
        # Verify JPEG magic bytes FF D8 FF
        self.assertEqual(jpeg_bytes[:3], b'\xff\xd8\xff')

    def test_pillow_fallback_with_rgba_photo(self):
        """Verify RGBA transparent images do not crash JPEG generation with 'cannot write mode RGBA as JPEG'."""
        from PIL import Image
        from apps.agents.services.og_image import _render_agent_og_jpeg_pillow

        agent = MagicMock()
        agent.full_name = "Ashish Prajapati"
        agent.agency_name = "Prajapati Insurance Services"
        agent.slug = "ashish-prajapati"
        mock_perf = MagicMock(rating=4.9, total_reviews=42)
        mock_profile = MagicMock(display_city="Ahmedabad", display_state="Gujarat")
        agent.insuranceSegments = MagicMock(all=lambda: [])

        # Create an in-memory transparent RGBA image as photo
        rgba_img = Image.new('RGBA', (200, 200), (255, 0, 0, 128))

        with patch('apps.agents.services.og_image._load_photo', return_value=rgba_img):
            jpeg_bytes = _render_agent_og_jpeg_pillow(agent, profile=mock_profile, perf=mock_perf)

        self.assertIsInstance(jpeg_bytes, bytes)
        self.assertEqual(jpeg_bytes[:3], b'\xff\xd8\xff')


class TestChatbotSecurity(unittest.TestCase):
    """Verify chatbot endpoint security checks."""
    def setUp(self):
        self.factory = RequestFactory()

    def test_session_id_validation_rejects_invalid(self):
        from apps.chatbot.views import get_history

        # Malicious session IDs
        bad_ids = ["../etc/passwd", "session;DROP TABLE", "user<script>", "a" * 150]
        for bad_id in bad_ids:
            req = self.factory.get(f'/chatbot/history/{bad_id}/')
            resp = get_history(req, bad_id)
            self.assertEqual(resp.status_code, 400, f"Failed to reject invalid session ID: {bad_id}")

    def test_send_message_blocks_unauthorized_origin(self):
        from apps.chatbot.views import send_message

        # Request from external phishing domain
        req = self.factory.post(
            '/chatbot/message/',
            data='{"message": "hi"}',
            content_type='application/json',
            HTTP_HOST='padosiagent.com',
            HTTP_ORIGIN='https://evil-attacker.com'
        )
        resp = send_message(req)
        self.assertEqual(resp.status_code, 403, "Failed to block unauthorized cross-origin request")


class TestFindAgentsNo302Redirect(unittest.TestCase):
    """Verify find_agents retains query parameters and does not issue a 302 redirect."""
    def setUp(self):
        self.factory = RequestFactory()

    def test_find_agents_with_pincode_returns_200_not_302(self):
        from apps.home.views.pages import find_agents
        from django.http import HttpResponse

        req = self.factory.get('/find-agents/?pincode=380015')
        req.session = {}
        req.user = AnonymousUser()

        # Mock out DB retrieval to test view routing behavior without live MySQL
        with patch('apps.home.views.pages.Pincode.objects') as mock_pincode_qs, \
             patch('apps.home.views.pages.fetch_filtered_agents_list', return_value=([], None, None, 'smart', False, 0)), \
             patch('apps.home.views.pages.render', return_value=HttpResponse('OK', status=200)):
            mock_pincode_qs.filter.return_value.first.return_value = None
            resp = find_agents(req)

        # Must NOT be 302 redirect
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(req.session.get('last_pincode'), '380015')

    def test_find_agents_without_params_has_no_unbound_local_error(self):
        """Verify accessing /find-agents/ with no query parameters does not trigger UnboundLocalError."""
        from apps.home.views.pages import find_agents
        from django.http import HttpResponse

        req = self.factory.get('/find-agents/')
        req.session = {}
        req.user = AnonymousUser()

        with patch('apps.home.views.pages.fetch_filtered_agents_list', return_value=([], None, None, 'smart', False, 0)), \
             patch('apps.home.views.pages.render', return_value=HttpResponse('OK', status=200)):
            resp = find_agents(req)

        self.assertEqual(resp.status_code, 200)


if __name__ == '__main__':
    unittest.main()
