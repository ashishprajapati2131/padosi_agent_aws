"""Mobile plan prices must match the website choose-plan settings."""
from django.test import SimpleTestCase

from apps.agents.views.registration import _get_tier_prices
from fastapi_app.services.plan_pricing import DEFAULT_PRICING, gst_bundle, quote_plan


class MobilePlanPricingTests(SimpleTestCase):
    def test_list_prices_are_admin_full_prices_until_scratch(self):
        starter = quote_plan(DEFAULT_PRICING, "starter", scratched=False, follow_count=0)
        professional = quote_plan(DEFAULT_PRICING, "professional", scratched=False, follow_count=4)
        self.assertEqual(starter["display_price"], 1999)
        self.assertEqual(starter["payable_total"], 2359)
        self.assertEqual(professional["display_price"], 9999)
        self.assertEqual(professional["price_after_scratch"], 7499)

    def test_scratch_and_follow_match_the_website(self):
        for follows in (0, 1, 2, 3, 4):
            website = _get_tier_prices(DEFAULT_PRICING, follows)
            starter = quote_plan(DEFAULT_PRICING, "starter", scratched=True, follow_count=follows)
            professional = quote_plan(
                DEFAULT_PRICING, "professional", scratched=True, follow_count=follows,
            )
            self.assertEqual(starter["display_price"], website["starter_base"])
            self.assertEqual(starter["payable_total"], website["starter_total"])
            self.assertEqual(professional["display_price"], website["prof_base"])
            self.assertEqual(professional["payable_total"], website["prof_total"])

    def test_one_follow_uses_the_admin_absolute_tier_price(self):
        starter = quote_plan(DEFAULT_PRICING, "starter", scratched=True, follow_count=1)
        self.assertEqual(starter["display_price"], 1399)
        self.assertEqual(gst_bundle(1999), (1999, 359.82, 2359))

    def test_referral_rupee_overrides_professional_only(self):
        professional = quote_plan(
            DEFAULT_PRICING, "professional", scratched=True, follow_count=4, force_rupee=True,
        )
        starter = quote_plan(DEFAULT_PRICING, "starter", scratched=False, follow_count=0)
        self.assertEqual(professional["payable_total"], 1)
        self.assertEqual(starter["display_price"], 1999)
