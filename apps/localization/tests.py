"""State-based language detection, /<lang>/ routing, switcher, SEO tags and admin config."""

from unittest import mock

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.test import TestCase
from django.utils import translation

from apps.localization import services
from apps.localization.models import (
    ContentTranslation,
    LocalizationSettings,
    SiteLanguage,
    StateLanguage,
    UserLanguagePreference,
)
from apps.localization.po import completion

BROWSER = (
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36"
)
GUJARAT = ("GJ", "Gujarat")


class LocalizationTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client.defaults["HTTP_USER_AGENT"] = BROWSER
        patcher = mock.patch.object(services, "lookup_indian_state", return_value=None)
        self.geo = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(translation.activate, "en")


class PrefixRoutingTests(LocalizationTestCase):
    def test_prefixed_page_renders_in_that_language_with_seo_tags(self):
        response = self.client.get("/gu/about/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Language"], "gu")
        html = response.content.decode()
        self.assertIn('<html lang="gu">', html)
        # Absolute URLs use the public site base (APP_URL), so match on the path.
        self.assertRegex(html, r'rel="canonical" href="https?://[^/"]+/gu/about/"')
        self.assertRegex(html, r'hreflang="hi" href="https?://[^/"]+/hi/about/"')
        self.assertRegex(html, r'hreflang="en" href="https?://[^/"]+/about/"')
        self.assertRegex(html, r'hreflang="x-default" href="https?://[^/"]+/about/"')
        self.assertIn("અમારા વિશે", html)  # "About Us" nav label

    def test_cached_pages_are_cached_per_language(self):
        # terms uses @cache_page and the stripped path is identical, so the cache key must
        # include the language; a shared entry would come back with Content-Language: en.
        self.assertEqual(self.client.get("/terms/")["Content-Language"], "en")
        self.assertEqual(self.client.get("/gu/terms/")["Content-Language"], "gu")

    def test_unprefixed_page_is_english_without_preference(self):
        response = self.client.get("/about/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('<html lang="en">', response.content.decode())
        self.assertIn("Accept-Language", response["Vary"])

    def test_source_language_prefix_redirects_to_unprefixed(self):
        response = self.client.get("/en/about/?a=1")
        self.assertRedirects(response, "/about/?a=1", fetch_redirect_response=False)

    def test_portal_requests_make_no_localization_queries(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as queries:
            self.client.post("/agent-register-step1/", {})
        self.assertFalse([q for q in queries if "localization_" in q["sql"]])

    def test_portal_paths_are_never_localized(self):
        response = self.client.get("/gu/agent-login/")
        self.assertRedirects(response, "/agent-login/", fetch_redirect_response=False)
        self.client.cookies["padosi_lang"] = "gu"
        response = self.client.get("/agent-login/")
        self.assertNotEqual(response.get("Location", ""), "/gu/agent-login/")

    def test_inactive_language_prefix_falls_back_to_unprefixed(self):
        SiteLanguage.objects.filter(code="or").update(is_active=False)
        services.clear_config_cache()
        response = self.client.get("/or/about/")
        self.assertRedirects(response, "/about/", fetch_redirect_response=False)

    def test_prefix_cannot_produce_protocol_relative_redirect(self):
        response = self.client.get("/en//evil.example/")
        self.assertTrue(response["Location"].startswith("/evil.example"))
        response = self.client.get("/en/\\evil.example/")
        self.assertFalse(response["Location"].startswith("//"))

    def test_existing_assam_agent_profile_url_still_wins(self):
        from apps.agents.models import Agent, AgentProfile

        user = User.objects.create_user("assam", "assam@example.com")
        agent = Agent.objects.create(
            user=user,
            fullname="A",
            email="assam@example.com",
            mobile="9876500001",
            status="active",
        )
        AgentProfile.objects.create(agent=agent, slug="ramesh-assam", display_name="A")
        self.assertEqual(
            services.split_language_prefix("/as/ramesh-assam/"),
            (None, "/as/ramesh-assam/"),
        )
        self.assertEqual(
            services.split_language_prefix("/as/about/"), ("as", "/about/")
        )
        self.assertEqual(
            services.split_language_prefix("/hi/ramesh-assam/"),
            ("hi", "/ramesh-assam/"),
        )


class DetectionPriorityTests(LocalizationTestCase):
    def test_gujarat_visitor_is_redirected_to_gujarati_and_query_kept(self):
        self.geo.return_value = GUJARAT
        response = self.client.get("/find-agents/?pincode=380001")
        self.assertRedirects(
            response, "/gu/find-agents/?pincode=380001", fetch_redirect_response=False
        )
        self.assertIn(services.GEO_COOKIE, response.cookies)
        self.assertEqual(response.cookies[services.GEO_COOKIE]["httponly"], True)

    def test_geo_result_is_reused_from_signed_cookie(self):
        self.geo.return_value = GUJARAT
        self.client.get("/about/")
        self.client.get("/about/")
        self.assertEqual(self.geo.call_count, 1)

    def test_tampered_geo_cookie_is_ignored(self):
        self.client.cookies[services.GEO_COOKIE] = "ta"
        response = self.client.get("/about/")
        self.assertEqual(response.status_code, 200)

    def test_each_mapped_state(self):
        expected = {
            "MH": "mr",
            "TN": "ta",
            "KA": "kn",
            "KL": "ml",
            "WB": "bn",
            "PB": "pa",
            "TS": "te",
            "AP": "te",
            "OD": "or",
            "AS": "as",
            "DL": "hi",
            "RJ": "hi",
            "UP": "hi",
        }
        config = services.get_config()
        for code, language in expected.items():
            self.assertEqual(
                services.language_for_state((code, ""), config), language, code
            )
        self.assertIsNone(services.language_for_state(("GA", "Goa"), config))
        self.assertEqual(
            services.language_for_state(
                ("", "National Capital Territory of Delhi"), config
            ),
            "hi",
        )

    def test_explicit_choice_beats_geoip(self):
        self.geo.return_value = GUJARAT
        self.client.cookies["padosi_lang"] = "en"
        response = self.client.get("/about/")
        self.assertEqual(response.status_code, 200)
        self.client.cookies["padosi_lang"] = "ta"
        self.assertRedirects(
            self.client.get("/about/"), "/ta/about/", fetch_redirect_response=False
        )

    def test_invalid_cookie_language_is_ignored(self):
        self.client.cookies["padosi_lang"] = "ur"
        self.assertEqual(self.client.get("/about/").status_code, 200)

    def test_saved_profile_preference_for_signed_in_user(self):
        user = User.objects.create_user("pref", "pref@example.com", "x")
        UserLanguagePreference.objects.create(user=user, language="kn")
        self.client.force_login(user)
        response = self.client.get("/about/")
        self.assertRedirects(response, "/kn/about/", fetch_redirect_response=False)
        self.assertEqual(response.cookies["padosi_lang"].value, "kn")

    def test_vpn_or_unknown_location_falls_back_to_browser_then_english(self):
        self.geo.return_value = None
        response = self.client.get(
            "/about/", HTTP_ACCEPT_LANGUAGE="hi-IN,hi;q=0.9,en;q=0.8"
        )
        self.assertRedirects(response, "/hi/about/", fetch_redirect_response=False)
        self.client.cookies.clear()
        self.assertEqual(
            self.client.get(
                "/about/", HTTP_ACCEPT_LANGUAGE="en-IN,en;q=0.9"
            ).status_code,
            200,
        )

    def test_admin_switches(self):
        self.geo.return_value = GUJARAT
        LocalizationSettings.objects.filter(pk=1).update(auto_detect_enabled=False)
        services.clear_config_cache()
        self.assertEqual(self.client.get("/about/").status_code, 200)
        self.assertEqual(self.geo.call_count, 0)

    def test_state_mapping_is_admin_configurable(self):
        self.geo.return_value = GUJARAT
        state = StateLanguage.objects.get(state_code="GJ")
        state.language_id = "hi"
        state.save()  # signal clears the cached config
        self.assertRedirects(
            self.client.get("/about/"), "/hi/about/", fetch_redirect_response=False
        )

    def test_bots_ajax_and_posts_are_never_redirected(self):
        self.client.cookies["padosi_lang"] = "gu"
        bot = self.client.get(
            "/about/", HTTP_USER_AGENT="Mozilla/5.0 (compatible; Googlebot/2.1)"
        )
        self.assertEqual(bot.status_code, 200)
        ajax = self.client.get("/about/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(ajax.status_code, 200)
        post = self.client.post("/contact/", {})
        self.assertNotEqual(post.get("Location", ""), "/gu/contact/")


class GeoLookupTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_private_and_invalid_ips_are_not_looked_up(self):
        with mock.patch.object(services, "_geoip_reader") as reader:
            self.assertIsNone(services.lookup_indian_state("127.0.0.1"))
            self.assertIsNone(services.lookup_indian_state("10.1.2.3"))
            self.assertIsNone(services.lookup_indian_state("not-an-ip"))
            reader.assert_not_called()

    def test_missing_database_is_graceful(self):
        with mock.patch.object(services, "_geoip_reader", return_value=None):
            self.assertIsNone(services.lookup_indian_state("49.36.0.1"))

    def test_indian_state_from_reader_and_cache(self):
        city = mock.Mock()
        city.country.iso_code = "IN"
        city.subdivisions.most_specific.iso_code = "GJ"
        city.subdivisions.most_specific.name = "Gujarat"
        reader = mock.Mock()
        reader.city.return_value = city
        with mock.patch.object(services, "_geoip_reader", return_value=reader):
            self.assertEqual(services.lookup_indian_state("49.36.0.1"), GUJARAT)
            self.assertEqual(services.lookup_indian_state("49.36.0.1"), GUJARAT)
        self.assertEqual(reader.city.call_count, 1)

    def test_foreign_ip_and_lookup_errors(self):
        reader = mock.Mock()
        reader.city.return_value.country.iso_code = "US"
        with mock.patch.object(services, "_geoip_reader", return_value=reader):
            self.assertIsNone(services.lookup_indian_state("8.8.8.8"))
        reader.city.side_effect = ValueError("bad record")
        with mock.patch.object(services, "_geoip_reader", return_value=reader):
            self.assertIsNone(services.lookup_indian_state("1.1.1.1"))


class SwitcherTests(LocalizationTestCase):
    def test_switch_keeps_page_and_query_and_sets_secure_cookie(self):
        response = self.client.post(
            "/i18n/setlang/", {"language": "hi", "next": "/find-agents/?pincode=380001"}
        )
        self.assertRedirects(
            response, "/hi/find-agents/?pincode=380001", fetch_redirect_response=False
        )
        cookie = response.cookies["padosi_lang"]
        self.assertEqual(cookie.value, "hi")
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")

    def test_switch_replaces_existing_prefix_and_english_drops_it(self):
        response = self.client.post(
            "/i18n/setlang/", {"language": "ta", "next": "/gu/faq/"}
        )
        self.assertRedirects(response, "/ta/faq/", fetch_redirect_response=False)
        response = self.client.post(
            "/i18n/setlang/", {"language": "en", "next": "/gu/faq/"}
        )
        self.assertRedirects(response, "/faq/", fetch_redirect_response=False)

    def test_invalid_language_and_offsite_next_are_rejected(self):
        response = self.client.post(
            "/i18n/setlang/", {"language": "xx", "next": "/faq/"}
        )
        self.assertRedirects(response, "/faq/", fetch_redirect_response=False)
        self.assertNotIn("padosi_lang", response.cookies)
        response = self.client.post(
            "/i18n/setlang/", {"language": "hi", "next": "https://evil.example/x"}
        )
        self.assertRedirects(response, "/hi/", fetch_redirect_response=False)
        response = self.client.post(
            "/i18n/setlang/", {"language": "hi", "next": "//evil.example/x"}
        )
        self.assertRedirects(response, "/hi/", fetch_redirect_response=False)

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get("/i18n/setlang/?language=hi").status_code, 405)

    def test_signed_in_choice_is_saved_to_profile(self):
        user = User.objects.create_user("sw", "sw@example.com", "x")
        self.client.force_login(user)
        self.client.post("/i18n/setlang/", {"language": "mr", "next": "/"})
        self.assertEqual(UserLanguagePreference.objects.get(user=user).language, "mr")

    def test_header_switcher_lists_native_names(self):
        html = self.client.get("/gu/about/").content.decode()
        self.assertIn('action="/i18n/setlang/"', html)
        self.assertIn('name="next" value="/about/"', html)
        for name in ("ગુજરાતી", "हिन्दी", "தமிழ்", "English"):
            self.assertIn(name, html)
        # Phone switcher sits outside the collapsed menu so it is always visible.
        self.assertLess(
            html.index('id="padosiLangMenuMobile"'),
            html.index('id="navbarSupportedContent"'),
        )


class GoogleTranslateLayerTests(LocalizationTestCase):
    FLAG = "apps.admin_panel.services.feature_flags.is_feature_enabled"

    def test_flag_on_translates_rest_of_page_into_selected_language(self):
        with mock.patch(self.FLAG, return_value=True):
            html = self.client.get("/gu/about/").content.decode()
        self.assertIn("translate_a/element.js", html)
        self.assertIn('var lang = "gu"', html)
        self.assertIn('class="header notranslate"', html)

    def test_english_page_clears_google_cookie_and_skips_script_mount(self):
        with mock.patch(self.FLAG, return_value=True):
            html = self.client.get("/about/").content.decode()
        self.assertIn('var lang = "en"', html)
        self.assertIn("expires=Thu, 01 Jan 1970", html)
        self.assertNotIn('id="padosi_google_translate_mount"', html)

    def test_flag_off_disables_google_translate(self):
        with mock.patch(self.FLAG, return_value=False):
            html = self.client.get("/gu/about/").content.decode()
        self.assertNotIn("translate_a/element.js", html)
        self.assertIn("અમારા વિશે", html)  # server-side translation still works


class LanguageLogoTests(LocalizationTestCase):
    def test_header_logo_follows_selected_language(self):
        self.assertIn(
            "img/logos/padosi-gu", self.client.get("/gu/about/").content.decode()
        )
        self.assertIn(
            "img/logos/padosi-ta", self.client.get("/ta/about/").content.decode()
        )
        self.assertIn(
            "img/logos/padosi-en", self.client.get("/about/").content.decode()
        )

    def test_every_site_language_has_a_logo_file(self):
        from pathlib import Path

        from django.conf import settings

        from apps.localization.context_processors import LANGUAGE_LOGO_WIDTHS

        for code, _name in settings.LANGUAGES:
            self.assertIn(code, LANGUAGE_LOGO_WIDTHS)
            self.assertTrue(
                (
                    Path(settings.BASE_DIR) / "static/img/logos" / f"padosi-{code}.webp"
                ).exists(),
                code,
            )


class SeoTests(LocalizationTestCase):
    def test_sitemap_has_language_urls_and_alternates(self):
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertIn("<loc>http://testserver/gu/about/</loc>", xml)
        self.assertIn('hreflang="x-default" href="http://testserver/about/"', xml)
        self.assertIn("<loc>http://testserver/hi/</loc>", xml)

    def test_sitemap_lists_portal_pages_once(self):
        from padosi_agent.sitemaps import StaticViewSitemap

        sitemap = StaticViewSitemap()
        with mock.patch.object(sitemap, "location", return_value="/agent-login/"):
            self.assertEqual(sitemap.get_languages_for_item("x"), ["en"])
        with mock.patch.object(sitemap, "location", return_value="/about/"):
            self.assertIn("gu", sitemap.get_languages_for_item("x"))

    def test_portal_pages_have_no_hreflang(self):
        html = self.client.get("/agent-login/").content.decode()
        self.assertNotIn('hreflang="gu"', html)


class ContentTranslationTests(LocalizationTestCase):
    def test_only_approved_translations_are_shown(self):
        from apps.home.models.page import Page

        page = Page.objects.create(
            title="Claims Help", slug="claims-help", content="<p>English body</p>"
        )
        ct = ContentType.objects.get_for_model(Page)
        row = ContentTranslation.objects.create(
            content_type=ct,
            object_id=str(page.pk),
            field="title",
            language="gu",
            text="ક્લેમ મદદ",
        )
        self.assertEqual(services.translated_field(page, "title", "gu"), "Claims Help")
        row.is_approved = True
        row.save()
        self.assertEqual(services.translated_field(page, "title", "gu"), "ક્લેમ મદદ")
        self.assertEqual(services.translated_field(page, "title", "en"), "Claims Help")
        self.assertEqual(
            services.translated_field(page, "content", "gu"), "<p>English body</p>"
        )


class AdminTests(LocalizationTestCase):
    def test_translation_completion(self):
        self.assertEqual(completion("gu")[0], completion("gu")[1])
        self.assertGreater(completion("gu")[1], 0)
        self.assertEqual(completion("en"), (1, 1))

    def test_source_language_cannot_be_disabled(self):
        english = SiteLanguage.objects.get(code="en")
        english.is_active = False
        english.save()
        self.assertTrue(SiteLanguage.objects.get(code="en").is_active)

    def test_django_admin_pages_load(self):
        admin = User.objects.create_superuser("root", "root@example.com", "x")
        self.client.force_login(admin)
        for url in (
            "/django-admin/localization/sitelanguage/",
            "/django-admin/localization/statelanguage/",
            "/django-admin/localization/localizationsettings/1/change/",
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)
