import json
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from apps.admin_panel.models import ContactSubmission
from apps.agents.models import Agent, AgentProfile, City
from apps.home import context_processors
from apps.home.models.site_setting import SiteSetting
from apps.home.views import pages


class QuickLeadPhoneEmailTests(TestCase):
    """WEB7: +91 / 0 prefixes are stripped, not truncated; email is validated."""

    def setUp(self):
        cache.clear()
        self.url = reverse("home:quick_lead_capture")

    def _post(self, **extra):
        data = {"name": "Asha", "mobile": "9876543210", **extra}
        return self.client.post(self.url, data=data)

    def test_plus91_prefix_keeps_real_number(self):
        self.assertEqual(self._post(mobile="+91 98765 43210").status_code, 200)
        self.assertTrue(ContactSubmission.objects.filter(mobile="9876543210").exists())

    def test_leading_zero_stripped(self):
        self.assertEqual(self._post(mobile="09876543210").status_code, 200)
        self.assertTrue(ContactSubmission.objects.filter(mobile="9876543210").exists())

    def test_bad_numbers_rejected(self):
        for bad in ["1234567890", "987654321012", "919876"]:
            with self.subTest(bad=bad):
                self.assertEqual(self._post(mobile=bad).status_code, 400)
        self.assertFalse(ContactSubmission.objects.exists())

    def test_invalid_email_rejected_valid_email_kept(self):
        self.assertEqual(self._post(email="not-an-email").status_code, 400)
        self.assertEqual(self._post(email="asha@example.com").status_code, 200)
        self.assertEqual(ContactSubmission.objects.get().email, "asha@example.com")


class FindAgentsTrackingPincodeTests(TestCase):
    """WEB10: a junk ?pincode= with lat/lng must not start analytics / card-seen alerts."""

    def _run(self, pincode):
        cache.clear()
        request = RequestFactory().get(
            "/find-agents/",
            {
                "pincode": pincode,
                "lat": "23.0",
                "lng": "72.5",
                "ServiceType": "New Policy",
            },
        )
        request.session = {}
        request.user = AnonymousUser()
        agents = [SimpleNamespace(id=1)]
        with (
            mock.patch.object(
                pages,
                "fetch_filtered_agents_list",
                return_value=(agents, 23.0, 72.5, "", False, 0),
            ),
            mock.patch.object(pages, "render", return_value=HttpResponse("ok")),
            mock.patch("threading.Thread") as thread,
        ):
            pages.find_agents(request)
        return thread

    def test_invalid_pincode_does_not_start_thread(self):
        self.assertFalse(self._run("<script>").called)

    def test_valid_pincode_starts_thread(self):
        self.assertTrue(self._run("380015").called)


@override_settings(ALLOWED_HOSTS=["*"])
class CityDirectoryCountTests(TestCase):
    """WEB11: sparse-result checks use a bounded COUNT (LIMIT), never a full-table count."""

    def test_count_queries_are_bounded(self):
        cache.clear()
        surat = City.objects.create(name="Surat", slug="surat", state="Gujarat")
        agent = Agent.objects.create(
            fullname="A One",
            email="a1@example.com",
            mobile="9876543210",
            status="active",
        )
        AgentProfile.objects.create(
            agent=agent, slug="a-one", display_name="A One", is_profile_visible=True
        )
        agent.serviceableCities.add(surat)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get("/insurance-agents/surat/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A One")
        counts = [
            q["sql"]
            for q in ctx.captured_queries
            if q["sql"]
            .upper()
            .startswith('SELECT COUNT(*) FROM (SELECT DISTINCT "AGENTS"')
        ]
        self.assertTrue(counts)
        for sql in counts:
            self.assertIn("LIMIT", sql.upper())


class BannerPopupBadJsonCacheTests(TestCase):
    """WEB13: invalid JSON is cached as {} so later requests skip the DB."""

    def setUp(self):
        cache.clear()

    def test_bad_json_cached_as_empty(self):
        request = RequestFactory().get("/")
        for key, setting, fn in [
            (
                "site_announcement_banner_data",
                "site_announcement_banner",
                context_processors.get_banner_config,
            ),
            (
                "site_exit_popup_data",
                "site_exit_popup",
                context_processors.get_exit_popup_config,
            ),
        ]:
            with self.subTest(setting=setting):
                with mock.patch.object(
                    SiteSetting, "get_value", return_value="{broken"
                ) as gv:
                    self.assertIsNone(fn(request))
                    self.assertIsNone(fn(request))
                self.assertEqual(cache.get(key), {})
                self.assertEqual(gv.call_count, 1)


class RobotsTxtRouteTests(TestCase):
    """WEB16: the project-level TemplateView serves robots.txt; the dead home view is gone."""

    def test_robots_resolves_to_template_view(self):
        match = resolve("/robots.txt")
        self.assertEqual(match.func.view_class.__name__, "TemplateView")
        from apps.home.views import seo

        self.assertFalse(hasattr(seo, "robots_txt"))
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Sitemap:", response.content.decode())
