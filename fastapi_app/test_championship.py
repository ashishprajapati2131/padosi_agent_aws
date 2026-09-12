import unittest
from fastapi_app.services.championship_service import (
    WHATSAPP_TEMPLATES,
    render_whatsapp_message,
    get_whatsapp_share_url,
    generate_qr_base64,
    generate_qr_bytes,
    format_inr,
)
from fastapi_app.schemas.championship import (
    UnlockProgressSchema,
    FunnelMetricsSchema,
    RewardSlabSchema,
    LeaderboardEntrySchema,
    ChampionshipDashboardResponse,
    WhatsAppShareRequest,
    WhatsAppShareResponse,
    RewardClaimRequest,
)


class TestChampionshipFastAPI(unittest.TestCase):

    def test_whatsapp_templates_presence(self):
        self.assertIn('en', WHATSAPP_TEMPLATES)
        self.assertIn('hi', WHATSAPP_TEMPLATES)
        self.assertIn('gu', WHATSAPP_TEMPLATES)
        self.assertIn('mr', WHATSAPP_TEMPLATES)

        # 9 languages total
        self.assertEqual(len(WHATSAPP_TEMPLATES), 9)

    def test_whatsapp_message_rendering(self):
        tmpl = WHATSAPP_TEMPLATES['gu']['templates'][0]['text']
        rendered = render_whatsapp_message(
            tmpl,
            agent_name="Rajesh Patel",
            referral_link="https://padosiagent.com/join/PA-123456",
            profile_link="https://padosiagent.com/agent/rajesh",
            digital_price=999,
            professional_price=4999
        )
        self.assertIn("Rajesh Patel", rendered)
        self.assertIn("PA-123456", rendered)
        self.assertIn("999", rendered)

    def test_whatsapp_url_generation(self):
        msg = "Hello World & PadosiAgent"
        url = get_whatsapp_share_url(msg)
        self.assertTrue(url.startswith("https://api.whatsapp.com/send?text="))
        self.assertIn("Hello%20World", url)

    def test_qr_code_generation(self):
        url = "https://padosiagent.com/agent-registration/join/PA-888999/"
        b64 = generate_qr_base64(url)
        self.assertTrue(b64.startswith("data:image/png;base64,"))

        b = generate_qr_bytes(url)
        self.assertTrue(isinstance(b, bytes))
        self.assertTrue(len(b) > 100)

    def test_inr_formatting(self):
        self.assertEqual(format_inr(999), "₹999")
        self.assertEqual(format_inr(9999), "₹9,999")
        self.assertEqual(format_inr(35000), "₹35,000")
        self.assertEqual(format_inr(250000), "₹2,50,000")

    def test_schemas_validation(self):
        req = RewardClaimRequest(slab_id=1, voucher_provider="amazon", shipping_address="Ahmedabad")
        self.assertEqual(req.voucher_provider, "amazon")

        share_req = WhatsAppShareRequest(language="gu", template_id="gu_1")
        self.assertEqual(share_req.language, "gu")


if __name__ == '__main__':
    unittest.main()
