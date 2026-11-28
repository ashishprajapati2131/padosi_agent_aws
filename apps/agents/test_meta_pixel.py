"""Meta Pixel: base PageView everywhere, CompleteRegistration after step 1, Purchase once per paid order."""

import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.agents.models import AgentDraft, AgentSubscription
from apps.agents import test_payment_approval_flow as flow
from apps.agents.views.registration_common import _meta_purchase_event

PIXEL = "2012064996398259"


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost"],
    RAZORPAY_WEBHOOK_SECRET="test_webhook_secret_key_123",
    META_PIXEL_ID=PIXEL,
)
class MetaPixelTests(TestCase):
    setUp = flow.PaymentToApprovalFlowTests.setUp
    _complete_step1_and_step2 = flow.PaymentToApprovalFlowTests._complete_step1_and_step2
    _create_order = flow.PaymentToApprovalFlowTests._create_order

    def test_pixel_on_registration_page_and_off_when_unset(self):
        html = self.client.get("/agent-registration/").content.decode()
        self.assertIn("fbevents.js", html)
        self.assertIn(f"PADOSI_META_PIXEL_ID = '{PIXEL}'", html)
        with self.settings(META_PIXEL_ID=""):
            self.assertNotIn(
                "fbevents.js", self.client.get("/agent-registration/").content.decode()
            )
        # Anything but digits is dropped, so the setting can never inject script.
        with self.settings(META_PIXEL_ID="1');alert(1);//"):
            self.assertNotIn(
                "alert(1)", self.client.get("/agent-registration/").content.decode()
            )

    def test_step1_success_returns_registration_event_id_only(self):
        r = self.client.post(
            "/agent-register-step1/",
            {
                "fullname": "Pixel Agent",
                "email": "pixel.agent@example.com",
                "mobile": "9876543210",
                "agent_pincode": "380001",
                "state": "Gujarat",
                "experience_range": "5",
                "segments[]": ["life"],
            },
        )
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        draft = AgentDraft.objects.get(email="pixel.agent@example.com")
        self.assertEqual(data["meta_event_id"], f"REG_{draft.pk}")

    def test_step1_error_has_no_event_id(self):
        r = self.client.post("/agent-register-step1/", {"fullname": "x"})
        self.assertNotIn("meta_event_id", r.content.decode())

    @patch("apps.agents.views.registration.queue_invoice_and_welcome")
    def test_verify_payment_returns_purchase_event(self, _queue):
        self._complete_step1_and_step2("pixel.pay@example.com")
        sub = self._create_order("starter", "order_PIXEL001")
        paise = int(round(float(sub.registration_amount) * 100))
        with patch(
            "apps.agents.views.registration.razorpay_client",
            return_value=flow._mock_razorpay_client(paise),
        ):
            r = self.client.post(
                "/agent-register/verify-payment/",
                data={
                    "razorpay_order_id": "order_PIXEL001",
                    "razorpay_payment_id": "pay_PIXEL001",
                    "razorpay_signature": flow.SIGNATURE,
                },
                content_type="application/json",
            )
        self.assertEqual(r.status_code, 200, r.content)
        mp = r.json()["meta_purchase"]
        self.assertEqual(mp["event_id"], f"PAY_{sub.pk}")
        self.assertEqual(mp["currency"], "INR")
        self.assertAlmostEqual(mp["value"], float(sub.registration_amount))

    @patch("apps.agents.views.registration.queue_invoice_and_welcome")
    def test_callback_purchase_fires_once_on_payment_complete(self, _queue):
        self._complete_step1_and_step2("pixel.cb@example.com")
        sub = self._create_order("starter", "order_PIXELCB01")
        paise = int(round(float(sub.registration_amount) * 100))
        with patch(
            "apps.agents.views.registration.razorpay_client",
            return_value=flow._mock_razorpay_client(paise),
        ):
            r = self.client.post(
                "/agent-register/payment-callback/",
                {
                    "razorpay_order_id": "order_PIXELCB01",
                    "razorpay_payment_id": "pay_PIXELCB01",
                    "razorpay_signature": flow.SIGNATURE,
                },
            )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(
            self.client.session["meta_purchase"]["event_id"], f"PAY_{sub.pk}"
        )
        with patch(
            "apps.agents.services.account_auth.agent_can_access_dashboard",
            return_value=True,
        ):
            first = self.client.get(
                "/agent-register/payment-complete/"
            ).content.decode()
            reload = self.client.get(
                "/agent-register/payment-complete/"
            ).content.decode()
        self.assertIn(f'"event_id": "PAY_{sub.pk}"', first)
        self.assertIn("metaPurchase: null", reload)

    def test_no_purchase_event_for_free_checkout(self):
        self._complete_step1_and_step2("pixel.free@example.com")
        sub = self._create_order("starter", "order_PIXELFREE")
        AgentSubscription.objects.filter(pk=sub.pk).update(
            payment_status="completed", registration_amount=0
        )
        self.assertIsNone(_meta_purchase_event(sub.agent))
