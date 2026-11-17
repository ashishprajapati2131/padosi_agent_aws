"""Admin panel (/admin/localization/) controls every part of the multilingual site."""

from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils import translation

from apps.admin_panel.services.feature_flags import is_feature_enabled
from apps.admin_panel.tests import authenticate_client
from apps.home.models.page import Page
from apps.home.models.site_setting import SiteSetting
from apps.localization import services
from apps.localization.models import (
    ContentTranslation,
    LocalizationSettings,
    SiteLanguage,
    StateLanguage,
    UITranslation,
)
from apps.localization.views import set_language  # noqa: F401  (route import sanity)

BROWSER = (
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36"
)
SETTINGS_ON = {
    "enabled": "1",
    "auto_detect_enabled": "1",
    "browser_language_enabled": "1",
    "google_translate": "1",
    "default_language": "en",
}


class LocalizationAdminPanelTests(TestCase):
    def setUp(self):
        cache.clear()
        authenticate_client(self.client)
        self.client.defaults["HTTP_USER_AGENT"] = BROWSER
        patcher = mock.patch.object(services, "lookup_indian_state", return_value=None)
        self.geo = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(translation.activate, "en")

    def test_every_tab_renders(self):
        Page.objects.create(title="Claims", slug="claims", content="<p>x</p>")
        for tab in ("settings", "languages", "states", "texts", "pages"):
            response = self.client.get(f"/admin/localization/?tab={tab}")
            self.assertEqual(response.status_code, 200, tab)
        page = Page.objects.get(slug="claims")
        self.assertEqual(
            self.client.get(
                f"/admin/localization/?tab=pages&page={page.pk}&lang=hi"
            ).status_code,
            200,
        )
        self.assertContains(
            self.client.get("/admin/localization/"), "Languages &amp; Localization"
        )

    def test_master_switch_off_makes_site_english_only(self):
        self.client.post(
            "/admin/localization/settings/", {**SETTINGS_ON, "enabled": ""}
        )
        self.assertFalse(LocalizationSettings.objects.get(pk=1).enabled)
        self.assertRedirects(
            self.client.get("/gu/about/"), "/about/", fetch_redirect_response=False
        )
        self.client.cookies["padosi_lang"] = "gu"
        html = self.client.get("/about/").content.decode()
        self.assertNotIn('action="/i18n/setlang/"', html)

    def test_ip_detection_switch(self):
        self.geo.return_value = ("GJ", "Gujarat")
        self.client.post(
            "/admin/localization/settings/", {**SETTINGS_ON, "auto_detect_enabled": ""}
        )
        self.assertEqual(self.client.get("/about/").status_code, 200)
        self.client.post("/admin/localization/settings/", SETTINGS_ON)
        self.assertRedirects(
            self.client.get("/about/"), "/gu/about/", fetch_redirect_response=False
        )

    def test_google_translate_switch_and_default_language(self):
        self.client.post(
            "/admin/localization/settings/",
            {**SETTINGS_ON, "google_translate": "", "default_language": "hi"},
        )
        self.assertFalse(
            is_feature_enabled("enable_multilingual_regional_branding", default=True)
        )
        self.assertEqual(
            LocalizationSettings.objects.get(pk=1).default_language_id, "hi"
        )
        SiteLanguage.objects.filter(code="ta").update(is_active=False)
        response = self.client.post(
            "/admin/localization/settings/", {**SETTINGS_ON, "default_language": "ta"}
        )
        self.assertEqual(
            LocalizationSettings.objects.get(pk=1).default_language_id, "hi"
        )
        self.assertEqual(response.status_code, 302)

    def test_languages_on_off_and_rename(self):
        data = {}
        for lang in SiteLanguage.objects.all():
            data.update(
                {
                    f"name_{lang.code}": lang.native_name,
                    f"order_{lang.code}": lang.sort_order,
                    f"active_{lang.code}": "1",
                }
            )
        data["active_ta"] = ""
        data["name_gu"] = "ગુજરાતી ભાષા"
        self.client.post("/admin/localization/languages/", data)
        self.assertFalse(SiteLanguage.objects.get(code="ta").is_active)
        self.assertTrue(SiteLanguage.objects.get(code="en").is_active)
        self.assertRedirects(
            self.client.get("/ta/about/"), "/about/", fetch_redirect_response=False
        )
        self.assertContains(self.client.get("/gu/about/"), "ગુજરાતી ભાષા")

    def test_state_language_map(self):
        gj = StateLanguage.objects.get(state_code="GJ")
        data = {
            f"lang_{s.pk}": s.language_id or "" for s in StateLanguage.objects.all()
        }
        data.update({f"aliases_{s.pk}": s.aliases for s in StateLanguage.objects.all()})
        data[f"lang_{gj.pk}"] = "mr"
        data[f"aliases_{gj.pk}"] = "GUJ"
        self.client.post("/admin/localization/states/", data)
        self.geo.return_value = ("GUJ", "")
        self.assertRedirects(
            self.client.get("/about/"), "/mr/about/", fetch_redirect_response=False
        )

    def test_website_text_edit_is_live_sanitized_and_revertible(self):
        key = "t_" + __import__("hashlib").sha1(b"About Us").hexdigest()[:16]
        self.client.post(
            "/admin/localization/texts/",
            {
                "lang": "gu",
                key: "અમારી ઓળખ<script>alert(1)</script>",
                "seo_meta_title": "ગુજરાતી શીર્ષક",
            },
        )
        self.assertEqual(
            UITranslation.objects.get(language="gu", msgid="About Us").text,
            "અમારી ઓળખalert(1)",
        )
        self.assertEqual(SiteSetting.get_value("seo_meta_title_gu"), "ગુજરાતી શીર્ષક")
        html = self.client.get("/gu/about/").content.decode()
        self.assertIn("અમારી ઓળખ", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.client.post("/admin/localization/texts/", {"lang": "gu", key: ""})
        self.assertFalse(
            UITranslation.objects.filter(language="gu", msgid="About Us").exists()
        )
        self.assertIn("અમારા વિશે", self.client.get("/gu/about/").content.decode())

    def test_english_text_can_be_edited_too(self):
        key = "t_" + __import__("hashlib").sha1(b"Contact Us").hexdigest()[:16]
        self.client.post(
            "/admin/localization/texts/", {"lang": "en", key: "Talk to us"}
        )
        self.assertIn("Talk to us", self.client.get("/about/").content.decode())

    def test_page_translation_draft_then_publish(self):
        page = Page.objects.create(
            title="Claims Help", slug="claims-help", content="<p>English body</p>"
        )
        post = {
            "page": page.pk,
            "lang": "gu",
            "title": "ક્લેમ મદદ",
            "meta_title": "",
            "meta_description": "",
            "content": "<p>ગુજરાતી</p>",
        }
        self.client.post("/admin/localization/pages/", post)
        self.assertEqual(
            ContentTranslation.objects.filter(object_id=str(page.pk)).count(), 2
        )
        self.assertNotIn(
            "ક્લેમ મદદ", self.client.get("/gu/claims-help/").content.decode()
        )
        self.client.post("/admin/localization/pages/", {**post, "approved": "1"})
        html = self.client.get("/gu/claims-help/").content.decode()
        self.assertIn("ક્લેમ મદદ", html)
        self.assertIn("ગુજરાતી", html)
        self.assertIn("English body", self.client.get("/claims-help/").content.decode())

    def test_requires_admin_session(self):
        self.client.cookies.pop("session_token")
        response = self.client.get("/admin/localization/")
        self.assertEqual(response.status_code, 302)
        self.client.post(
            "/admin/localization/settings/", {**SETTINGS_ON, "enabled": ""}
        )
        self.assertTrue(LocalizationSettings.objects.get(pk=1).enabled)
