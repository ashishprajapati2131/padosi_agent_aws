from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.home.models.site_setting import SiteSetting
from apps.wholesale.models.category import ProductCategory
from apps.wholesale.models.pricing import WholesalePriceTier
from apps.wholesale.models.product import WholesaleProduct
from apps.wholesale.models.profile import WholesalerProfile
from apps.wholesale.services.pricing_service import PricingService

User = get_user_model()


class WholesalePricingServiceWhiteBoxTests(TestCase):
    """
    White-Box Unit and Boundary Tests for Wholesale PricingService.
    Covers tier validation logic, boundary numbers, ordering, gaps, and order summary math.
    """

    def setUp(self):
        self.user = User.objects.create_user("wholesaler_wb", "wb@example.com", "SecretPass123!")
        self.wholesaler = WholesalerProfile.objects.create(
            user=self.user,
            business_name="Wholesale WB Ltd",
            contact_person="Ramesh Patel",
            email="wb@example.com",
            phone="9879000001",
            city="Ahmedabad",
            state="Gujarat",
            verification_status="APPROVED",
        )
        self.category = ProductCategory.objects.create(
            name="Packaging Material", slug="packaging-mat", is_active=True
        )
        self.product = WholesaleProduct.objects.create(
            wholesaler=self.wholesaler,
            category=self.category,
            title="Premium Document Envelope",
            slug="premium-doc-envelope",
            sku="WS-ENV-001",
            moq=10,
            base_price=Decimal("50.00"),
            suggested_retail_price=Decimal("100.00"),
            approval_status="PUBLISHED",
            tax_included=True,
            tax_rate_percent=Decimal("18.00"),
        )

    def test_validate_tiers_empty_returns_no_errors(self):
        """Boundary: Empty tier list is valid."""
        errors = PricingService.validate_tiers(self.product, [])
        self.assertEqual(errors, [])

    def test_validate_tiers_single_valid_tier(self):
        """Positive: Single valid tier."""
        tiers = [{"min_qty": 10, "max_qty": 49, "price": 45.0}]
        errors = PricingService.validate_tiers(self.product, tiers)
        self.assertEqual(errors, [])

    def test_validate_tiers_contiguous_multi_tier(self):
        """Positive: Perfectly contiguous tiers with monotonic decreasing price."""
        tiers = [
            {"min_qty": 10, "max_qty": 49, "price": 45.0},
            {"min_qty": 50, "max_qty": 99, "price": 40.0},
            {"min_qty": 100, "max_qty": None, "price": 35.0},
        ]
        errors = PricingService.validate_tiers(self.product, tiers)
        self.assertEqual(errors, [])

    def test_validate_tiers_rejects_min_qty_less_than_one(self):
        """Negative / Boundary: Minimum quantity < 1 rejected."""
        tiers = [{"min_qty": 0, "max_qty": 49, "price": 45.0}]
        errors = PricingService.validate_tiers(self.product, tiers)
        self.assertTrue(any("must be at least 1" in e for e in errors))

    def test_validate_tiers_rejects_min_greater_than_max(self):
        """Negative / Boundary: min_qty > max_qty rejected."""
        tiers = [{"min_qty": 50, "max_qty": 20, "price": 45.0}]
        errors = PricingService.validate_tiers(self.product, tiers)
        self.assertTrue(any("cannot exceed Max quantity" in e for e in errors))

    def test_validate_tiers_rejects_overlapping_ranges(self):
        """Negative: Overlapping tier intervals rejected."""
        tiers = [
            {"min_qty": 10, "max_qty": 50, "price": 45.0},
            {"min_qty": 45, "max_qty": 99, "price": 40.0},
        ]
        errors = PricingService.validate_tiers(self.product, tiers)
        self.assertTrue(any("Overlaps with previous tier" in e for e in errors))

    def test_validate_tiers_rejects_gaps_between_tiers(self):
        """Negative: Non-contiguous gap between tiers rejected."""
        tiers = [
            {"min_qty": 10, "max_qty": 49, "price": 45.0},
            {"min_qty": 55, "max_qty": 99, "price": 40.0},  # Gap: 50-54 missing
        ]
        errors = PricingService.validate_tiers(self.product, tiers)
        self.assertTrue(any("gap between 49 and 55" in e for e in errors))

    def test_validate_tiers_rejects_price_increase_on_volume(self):
        """Negative / Business rule: Volume unit price cannot increase at higher volume."""
        tiers = [
            {"min_qty": 10, "max_qty": 49, "price": 40.0},
            {"min_qty": 50, "max_qty": 99, "price": 45.0},  # Higher price for higher quantity
        ]
        errors = PricingService.validate_tiers(self.product, tiers)
        self.assertTrue(any("should be less than or equal to previous tier" in e for e in errors))

    def test_validate_tiers_open_ended_must_be_last(self):
        """Negative: Open-ended tier (no max_qty) placed before other tiers rejected."""
        tiers = [
            {"min_qty": 10, "max_qty": None, "price": 45.0},
            {"min_qty": 50, "max_qty": 99, "price": 40.0},
        ]
        errors = PricingService.validate_tiers(self.product, tiers)
        self.assertTrue(any("Open-ended tier" in e for e in errors))

    def test_calculate_order_summary_accurate_pricing_and_savings(self):
        """Positive / Math verification: Exact order calculation across tier boundaries."""
        tiers = [
            {"min_qty": 10, "max_qty": 49, "price": 45.0},
            {"min_qty": 50, "max_qty": 99, "price": 40.0},
            {"min_qty": 100, "max_qty": None, "price": 30.0},
        ]
        PricingService.save_tiers_for_product(self.product, tiers)

        # Quantity 60 lands in tier 2 (price 40.0)
        summary = PricingService.calculate_order_summary(self.product, 60)
        self.assertEqual(summary["quantity"], 60)
        self.assertEqual(summary["unit_price"], Decimal("40.00"))
        self.assertEqual(summary["total_base"], Decimal("2400.00"))
        self.assertEqual(summary["total_with_tax"], Decimal("2400.00"))


class WholesaleDRFViewsetWhiteBoxTests(TestCase):
    """
    White-Box Integration Tests for Wholesale DRF API Endpoints.
    """

    def setUp(self):
        SiteSetting.set_value("wholesale_marketplace_enabled", "1", group="general")
        self.client = APIClient()

        self.user = User.objects.create_user("wholesaler_api", "api@example.com", "SecretPass123!")
        self.wholesaler = WholesalerProfile.objects.create(
            user=self.user,
            business_name="Prime Office Wholesale",
            contact_person="Vikas Shah",
            email="api@example.com",
            phone="9879000002",
            city="Surat",
            state="Gujarat",
            verification_status="APPROVED",
        )
        self.category = ProductCategory.objects.create(
            name="Brochures & Flyers", slug="brochures-flyers", is_active=True, sort_order=1
        )
        self.product = WholesaleProduct.objects.create(
            wholesaler=self.wholesaler,
            category=self.category,
            title="Custom Glossy Agent Brochure",
            slug="custom-glossy-agent-brochure",
            sku="WS-BRO-001",
            moq=25,
            base_price=Decimal("15.00"),
            suggested_retail_price=Decimal("35.00"),
            approval_status="PUBLISHED",
            is_featured=True,
        )

        # Unapproved product from unverified wholesaler to test access control filtering
        self.unverified_user = User.objects.create_user("unverified_ws", "unv@example.com", "SecretPass123!")
        self.unverified_wholesaler = WholesalerProfile.objects.create(
            user=self.unverified_user,
            business_name="Unverified Supplier",
            contact_person="X",
            email="unv@example.com",
            phone="9879000003",
            city="Surat",
            state="Gujarat",
            verification_status="PENDING",
        )
        self.hidden_product = WholesaleProduct.objects.create(
            wholesaler=self.unverified_wholesaler,
            category=self.category,
            title="Hidden Draft Flyer",
            slug="hidden-draft-flyer",
            sku="WS-HID-001",
            moq=10,
            base_price=Decimal("10.00"),
            suggested_retail_price=Decimal("20.00"),
            approval_status="DRAFT",
        )

    def test_public_product_list_excludes_unapproved_and_unverified(self):
        """Security / Data isolation: Unapproved/unverified products must NEVER appear in public catalog."""
        resp = self.client.get("/wholesale/api/v1/products/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        slugs = [p["slug"] for p in resp.data]
        self.assertIn("custom-glossy-agent-brochure", slugs)
        self.assertNotIn("hidden-draft-flyer", slugs)

    def test_public_product_search_filter(self):
        """Positive / Filter: Query parameter `q` searches title and SKU."""
        resp = self.client.get("/wholesale/api/v1/products/?q=Glossy")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["slug"], "custom-glossy-agent-brochure")

        # Non-matching query
        resp_empty = self.client.get("/wholesale/api/v1/products/?q=NonExistentKeywordXYZ")
        self.assertEqual(resp_empty.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_empty.data), 0)

    def test_calculate_price_action_endpoint(self):
        """Positive / Contract: DRF action calculate_price returns expected schema."""
        WholesalePriceTier.objects.create(
            product=self.product, min_quantity=25, max_quantity=99, unit_price=Decimal("12.00")
        )
        resp = self.client.get(f"/wholesale/api/v1/products/{self.product.slug}/calculate_price/?quantity=50")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["quantity"], 50)
        self.assertEqual(resp.data["unit_price"], Decimal("12.00"))
        self.assertEqual(resp.data["total_base"], Decimal("600.00"))

    def test_calculate_price_action_invalid_quantity_falls_back_to_moq(self):
        """Boundary: Invalid non-numeric quantity gracefully falls back to product MOQ."""
        resp = self.client.get(f"/wholesale/api/v1/products/{self.product.slug}/calculate_price/?quantity=invalid_abc")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["quantity"], self.product.moq)

    def test_public_categories_list(self):
        """Positive: Public categories list returns active categories."""
        resp = self.client.get("/wholesale/api/v1/categories/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        slugs = [c["slug"] for c in resp.data]
        self.assertIn("brochures-flyers", slugs)

    def test_buyer_inquiry_creation_validation(self):
        """Negative: Quotation submission requires valid buyer details and product."""
        # Missing required fields
        resp = self.client.post("/wholesale/api/v1/inquiries/", data={}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Valid payload
        valid_payload = {
            "product": self.product.id,
            "buyer_name": "Agent Suresh",
            "buyer_email": "suresh@example.com",
            "buyer_phone": "9825000001",
            "delivery_pincode": "380001",
            "delivery_city": "Ahmedabad",
            "requested_quantity": 50,
            "message": "Please stamp with Suresh Insurance Consultancy",
        }
        resp_valid = self.client.post("/wholesale/api/v1/inquiries/", data=valid_payload, format="json")
        self.assertEqual(resp_valid.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp_valid.data["success"])
        self.assertIn("inquiry_id", resp_valid.data)
