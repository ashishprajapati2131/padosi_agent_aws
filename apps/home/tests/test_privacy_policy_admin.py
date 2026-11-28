"""Privacy policy admin CRUD and the public page that reads it."""
from datetime import date
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.admin_panel.views.privacy_policy import (
    privacy_delete,
    privacy_publish,
    privacy_store,
    privacy_update,
)
from apps.home.models.privacy_policy import PrivacyPolicy
from apps.home.privacy_content import GRIEVANCE_EMAIL


def _request(method, path, data=None):
    factory = RequestFactory()
    request = factory.post(path, data or {}) if method == "POST" else factory.get(path)
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)
    return request


def _fields(**overrides):
    data = {
        "title": "Privacy Policy",
        "effective_date": "2026-11-27",
        "company_name": "PadosiAgent ServTech Private Limited",
        "address": "Ahmedabad, Gujarat, India",
        "contact_email": "support@padosiagent.com",
        "grievance_email": GRIEVANCE_EMAIL,
        "content": "<p>Policy body for the test.</p>",
        "is_published": "on",
    }
    data.update(overrides)
    return data


class PrivacyPolicyAdminTests(TestCase):
    def setUp(self):
        self.seed = PrivacyPolicy.objects.get(is_published=True)

    def _call(self, view, request, **kwargs):
        with patch(
            "apps.admin_panel.views.privacy_policy._get_admin_from_session",
            return_value=1,
        ):
            return view(request, **kwargs)

    def test_public_page_uses_published_policy_and_logo(self):
        self.seed.grievance_email = "padosiagent@gmail.com"
        self.seed.content = "<p>Advertising ID stays in the published policy.</p>"
        self.seed.save()
        response = self.client.get("/privacy/")
        body = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('alt="PadosiAgent"', body)
        self.assertIn("padosiagent@gmail.com", body)
        self.assertIn("Advertising ID stays in the published policy.", body)
        self.assertNotIn("privacy@padosiagent.com", body)

    def test_store_publishes_one_policy_and_strips_scripts(self):
        response = self._call(
            privacy_store,
            _request("POST", "/admin/privacy-policy/store/", _fields(
                title="Revised policy",
                content="<p>Visible text.</p><script>alert(1)</script>",
            )),
        )
        self.assertEqual(response.status_code, 302)
        self.seed.refresh_from_db()
        self.assertFalse(self.seed.is_published)
        revised = PrivacyPolicy.objects.get(title="Revised policy")
        self.assertTrue(revised.is_published)
        self.assertNotIn("<script", revised.content)
        self.assertIn("Visible text.", revised.content)
        public = self.client.get("/privacy/").content.decode()
        self.assertIn("Revised policy", public)
        self.assertIn("Visible text.", public)
        self.assertNotIn("alert(1)", public)

    def test_invalid_email_is_not_saved(self):
        before = PrivacyPolicy.objects.count()
        response = self._call(
            privacy_store,
            _request("POST", "/admin/privacy-policy/store/", _fields(
                grievance_email="not-an-email",
            )),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PrivacyPolicy.objects.count(), before)

    def test_update_changes_the_live_page(self):
        response = self._call(
            privacy_update,
            _request("POST", f"/admin/privacy-policy/{self.seed.id}/update/", _fields(
                title="Edited policy",
                grievance_email="padosiagent@gmail.com",
                content="<p>Edited from the admin.</p>",
            )),
            policy_id=self.seed.id,
        )
        self.assertEqual(response.status_code, 302)
        public = self.client.get("/privacy/").content.decode()
        self.assertIn("Edited policy", public)
        self.assertIn("Edited from the admin.", public)

    def test_deleting_the_published_policy_promotes_the_newest_draft(self):
        draft = PrivacyPolicy.objects.create(
            title="Older draft",
            effective_date=date(2026, 11, 1),
            company_name="PadosiAgent ServTech Private Limited",
            address="Ahmedabad, Gujarat, India",
            contact_email="support@padosiagent.com",
            grievance_email="padosiagent@gmail.com",
            content="<p>Promoted draft.</p>",
            is_published=False,
        )
        response = self._call(
            privacy_delete,
            _request("POST", f"/admin/privacy-policy/{self.seed.id}/delete/"),
            policy_id=self.seed.id,
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PrivacyPolicy.objects.filter(pk=self.seed.pk).exists())
        draft.refresh_from_db()
        self.assertTrue(draft.is_published)
        self.assertIn("Promoted draft.", self.client.get("/privacy/").content.decode())

    def test_publish_button_makes_a_draft_live(self):
        draft = PrivacyPolicy.objects.create(
            title="Waiting to go live",
            effective_date=date(2026, 11, 27),
            company_name="PadosiAgent ServTech Private Limited",
            address="Ahmedabad, Gujarat, India",
            contact_email="support@padosiagent.com",
            grievance_email="padosiagent@gmail.com",
            content="<p>This draft is now live.</p>",
            is_published=False,
        )
        response = self._call(
            privacy_publish,
            _request("POST", f"/admin/privacy-policy/{draft.id}/publish/"),
            policy_id=draft.id,
        )
        self.assertEqual(response.status_code, 302)
        draft.refresh_from_db()
        self.seed.refresh_from_db()
        self.assertTrue(draft.is_published)
        self.assertFalse(self.seed.is_published)
        self.assertIn("This draft is now live.", self.client.get("/privacy/").content.decode())

    def test_anonymous_admin_is_sent_to_login(self):
        request = _request("GET", "/admin/privacy-policy/")
        with patch(
            "apps.admin_panel.views.privacy_policy._get_admin_from_session",
            return_value=None,
        ):
            from apps.admin_panel.views.privacy_policy import privacy_index
            response = privacy_index(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/")
