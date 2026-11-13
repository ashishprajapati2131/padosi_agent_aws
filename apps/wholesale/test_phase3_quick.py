"""Audit phase 3 quick fixes: INS6 (editing a live product re-enters review),
INS11 (public product endpoints only for published products, variant must
belong to the product), INS13 (quote amount is a positive finite Decimal)."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.wholesale.forms.product_forms import ProductWizardForm
from apps.wholesale.models.inquiry import BuyerInquiry
from apps.wholesale.models.product import ProductVariant, WholesaleProduct
from apps.wholesale.services.rfq_service import RFQService
from apps.wholesale.test_security import WholesaleSecurityBase


class WholesalePhase3Tests(WholesaleSecurityBase):
    def _inquiry(self):
        return BuyerInquiry.objects.create(
            product=self.product,
            wholesaler=self.profile,
            buyer_name="B",
            buyer_email="b@example.com",
            buyer_phone="9898000102",
            delivery_pincode="380015",
            delivery_city="Ahmedabad",
            requested_quantity=5,
        )

    def test_editing_published_product_goes_back_to_review(self):
        self.client.force_login(self.user)
        form = ProductWizardForm(instance=self.product)
        data = {
            k: v for k, v in form.initial.items() if k in form.fields and v is not None
        }
        data["title"] = "Sec Folder v2"
        data["wizard_action"] = "save_draft"
        resp = self.client.post(
            reverse("wholesale:product_edit", args=[self.product.pk]), data
        )
        self.assertEqual(resp.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.title, "Sec Folder v2")
        self.assertEqual(self.product.approval_status, "SUBMITTED")

    def test_unpublished_product_hidden_from_public_endpoints(self):
        WholesaleProduct.objects.filter(pk=self.product.pk).update(
            approval_status="DRAFT"
        )
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse("wholesale:calculate_price_api", args=[self.product.pk])
        )
        self.assertEqual(resp.status_code, 404)
        resp = self.client.post(
            reverse("wholesale:submit_rfq", args=[self.product.pk]), {"buyer_name": "B"}
        )
        self.assertEqual(resp.status_code, 404)

    def test_published_product_price_api_still_works(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse("wholesale:calculate_price_api", args=[self.product.pk])
        )
        self.assertEqual(resp.status_code, 200)

    def test_variant_from_other_product_rejected(self):
        other = WholesaleProduct.objects.create(
            wholesaler=self.profile,
            category=self.product.category,
            title="Other",
            slug="other-p3",
            sku="WS-SEC-002",
            short_description="x",
            description="x",
            moq=1,
            base_price=Decimal("10.00"),
            suggested_retail_price=Decimal("20.00"),
            approval_status="PUBLISHED",
        )
        variant = ProductVariant.objects.create(product=other, name="V", sku="V-1")
        with self.assertRaises(ValidationError):
            RFQService.submit_inquiry(
                self.product,
                {
                    "requested_quantity": 1,
                    "variant_id": variant.pk,
                    "buyer_name": "B",
                    "buyer_email": "b@example.com",
                    "buyer_phone": "9898000102",
                    "delivery_city": "A",
                    "delivery_pincode": "380015",
                    "message": "m",
                },
            )

    def test_bad_quote_amounts_rejected_good_one_saved(self):
        inquiry = self._inquiry()
        self.client.force_login(self.user)
        url = reverse("wholesale:rfq_reply", args=[inquiry.pk])
        for bad in ("0", "-5", "NaN", "inf", "abc"):
            self.client.post(url, {"action_type": "quote", "quote_amount": bad})
            inquiry.refresh_from_db()
            self.assertIsNone(inquiry.seller_quotation_amount, bad)
        self.client.post(url, {"action_type": "quote", "quote_amount": "99.50"})
        inquiry.refresh_from_db()
        self.assertEqual(inquiry.seller_quotation_amount, Decimal("99.50"))
