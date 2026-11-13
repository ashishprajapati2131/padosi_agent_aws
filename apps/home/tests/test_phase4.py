"""Phase 4 audit regressions: WEB9 session writes, WEB14 lead forms, WEB8 review annotations."""

from unittest.mock import patch

from django.contrib.sessions.backends.cache import SessionStore
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.db.models import Value
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.admin_panel.models.contact_submission import ContactSubmission
from apps.agents.models import Agent, AgentProfile, AgentReview
from apps.home.views import pages


class SessionWriteTests(TestCase):
    def test_unchanged_value_does_not_mark_session_modified(self):
        session = SessionStore()
        session["last_pincode"] = "380007"
        session.modified = False
        pages._set_session_if_changed(session, "last_pincode", "380007")
        self.assertFalse(session.modified)
        pages._set_session_if_changed(session, "last_pincode", "380008")
        self.assertTrue(session.modified)

    def test_coords_must_be_floats_inside_india(self):
        self.assertTrue(pages._coords_in_india("23.02", "72.57"))
        for lat, lng in [
            ("abc", "72"),
            ("51.5", "-0.1"),
            ("nan", "nan"),
            ("23", "120"),
        ]:
            self.assertFalse(pages._coords_in_india(lat, lng), (lat, lng))


@patch.object(
    pages,
    "fetch_filtered_agents_list",
    return_value=([], None, None, "rating", False, 165),
)
@patch.object(pages.GeocodingService, "resolve_coordinates", return_value=None)
class FindAgentsSessionTests(TestCase):
    def test_valid_pincode_is_stored(self, *_):
        self.client.get(reverse("home:find_agents"), {"pincode": "380007"})
        self.assertEqual(self.client.session["last_pincode"], "380007")

    def test_invalid_pincode_is_not_stored(self, *_):
        self.client.get(reverse("home:find_agents"), {"pincode": "<script>"})
        self.assertNotIn("last_pincode", self.client.session)
        self.assertNotIn("detected_area", self.client.session)

    def test_coords_outside_india_are_not_stored(self, *_):
        self.client.get(reverse("home:find_agents"), {"lat": "51.5", "lng": "-0.12"})
        self.assertNotIn("last_lat", self.client.session)
        self.client.get(reverse("home:find_agents"), {"lat": "23.02", "lng": "72.57"})
        self.assertEqual(self.client.session["last_lat"], "23.02")


CONTACT = {
    "name": "Asha Shah",
    "mobile": "9876500000",
    "email": "asha@example.com",
    "subject": "Policy question",
    "message": "Please call me about a health plan.",
}
LEAD = {"name": "Asha", "mobile": "9876500000", "pincode": "380007"}
QUICK_LEAD_URL = "/api/quick-lead-capture/"


class LeadFormAbuseTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_contact_honeypot_returns_success_without_saving(self):
        resp = self.client.post(
            reverse("home:contact_submit"), {**CONTACT, "website_url": "http://spam"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])
        self.assertEqual(ContactSubmission.objects.count(), 0)

    def test_quick_lead_honeypot_returns_success_without_saving(self):
        resp = self.client.post(QUICK_LEAD_URL, {**LEAD, "website_url": "http://spam"})
        self.assertEqual(resp.json()["status"], "success")
        self.assertEqual(ContactSubmission.objects.count(), 0)

    def test_quick_lead_counts_failed_attempts(self):
        for _ in range(pages.QUICK_LEAD_MAX_PER_IP):
            self.client.post(QUICK_LEAD_URL, {"name": "x"})
        self.assertEqual(self.client.post(QUICK_LEAD_URL, LEAD).status_code, 429)
        self.assertEqual(ContactSubmission.objects.count(), 0)

    def test_quick_lead_still_saves_normal_lead(self):
        resp = self.client.post(QUICK_LEAD_URL, LEAD)
        self.assertEqual(resp.json()["status"], "success")
        self.assertEqual(ContactSubmission.objects.count(), 1)

    def test_templates_render_hidden_honeypot(self):
        html = self.client.get(reverse("home:contact")).content.decode()
        self.assertIn('name="website_url"', html)
        self.assertIn('tabindex="-1"', html)


# The smart-rank RawSQL is MySQL-only; the test DB is SQLite.
@patch.object(pages, "RawSQL", lambda sql, params: Value(0))
class ReviewAnnotationTests(TestCase):
    def setUp(self):
        self.agent = Agent.objects.create(
            fullname="Rate Me",
            email="rate@example.com",
            mobile="9876543210",
            status="active",
        )
        AgentProfile.objects.create(
            agent=self.agent,
            slug="rate-me",
            display_name="Rate Me",
            is_profile_visible=True,
        )
        for rating, approved in [(5, True), (4, True), (4, True), (1, False)]:
            AgentReview.objects.create(
                agent=self.agent, rating=rating, is_approved=approved
            )

    def _request(self):
        request = RequestFactory().get("/find-agents/")
        SessionMiddleware(lambda r: None).process_request(request)
        return request

    def test_rating_and_count_match_model_without_prefetching_reviews(self):
        agents = pages.fetch_filtered_agents_list(self._request())[0]
        found = next(a for a in agents if a.pk == self.agent.pk)
        self.assertNotIn("reviews", getattr(found, "_prefetched_objects_cache", {}))
        fresh = Agent.objects.prefetch_related("reviews").get(pk=self.agent.pk)
        self.assertEqual(found.average_rating, fresh.average_rating)
        self.assertEqual(found.review_count, fresh.review_count)
        self.assertEqual(found.review_count, 3)

    def test_agent_without_reviews_rates_zero(self):
        AgentReview.objects.all().delete()
        agents = pages.fetch_filtered_agents_list(self._request())[0]
        found = next(a for a in agents if a.pk == self.agent.pk)
        self.assertEqual((found.average_rating, found.review_count), (0.0, 0))
