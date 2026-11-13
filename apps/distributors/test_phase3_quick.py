"""Audit phase 3 quick fixes: INS8 (profile password check), INS9 (no
auth_user.id fallback for the distributor id), INS11 (cross-sell only published
products), INS14 (no exception text to clients)."""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.admin_panel.models import User as LaravelUser
from apps.agents.models import Agent
from apps.distributors.models import SubDistributor
from apps.wholesale.models.category import ProductCategory
from apps.wholesale.models.inquiry import BuyerInquiry
from apps.wholesale.models.product import WholesaleProduct
from apps.wholesale.models.profile import WholesalerProfile
from password_hashing import hash_password


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class DistributorPhase3Tests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "p3d@example.com", "p3d@example.com", "oldpass123"
        )
        self.user.groups.add(Group.objects.get_or_create(name="distributor")[0])
        self.client.force_login(self.user)

    def _change_password(self, current):
        return self.client.post(
            reverse("distributors:profile_update"),
            {
                "fullname": "P3 Dist",
                "email": "p3d@example.com",
                "current_password": current,
                "password": "newpass123",
                "password_confirmation": "newpass123",
            },
        )

    def test_wrong_current_password_rejected_without_laravel_user(self):
        self._change_password("wrong")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("oldpass123"))

    def test_non_bcrypt_laravel_hash_does_not_crash(self):
        LaravelUser.objects.create(
            fullname="P3",
            email="p3d@example.com",
            password="plain-not-bcrypt",
            role="distributor",
            status="active",
        )
        resp = self._change_password("wrong")
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("oldpass123"))

    def test_correct_password_still_changes(self):
        self._change_password("oldpass123")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newpass123"))

    def test_missing_fields_do_not_crash(self):
        resp = self.client.post(reverse("distributors:profile_update"), {})
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "p3d@example.com")

    def test_no_laravel_row_denies_access_to_matching_auth_id(self):
        # An agent / sub-distributor whose distributor_id equals this auth_user.id must stay hidden.
        Agent.objects.create(
            fullname="Other",
            email="o3@example.com",
            mobile="9000000391",
            status="active",
            distributor_id=self.user.id,
        )
        sub = SubDistributor.objects.create(
            distributor_id=self.user.id,
            fullname="S",
            email="s3@example.com",
            mobile="9000000392",
            password=hash_password("x12345678"),
            code="P3SUB",
            status="active",
        )
        resp = self.client.get(reverse("distributors:agents_index"))
        self.assertEqual(resp.status_code, 302)
        resp = self.client.post(
            reverse("distributors:sub_distributor_toggle_status", args=[sub.pk])
        )
        self.assertEqual(resp.status_code, 404)
        sub.refresh_from_db()
        self.assertEqual(sub.status, "active")

    def test_cross_sell_order_rejects_unpublished_product(self):
        ws_user = User.objects.create_user("p3ws", "p3ws@example.com", "x")
        profile = WholesalerProfile.objects.create(
            user=ws_user,
            business_name="P3 WS",
            contact_person="W",
            email="p3ws@example.com",
            phone="9898000301",
            city="A",
            state="G",
            verification_status="APPROVED",
        )
        cat = ProductCategory.objects.create(
            name="P3 Cat", slug="p3-cat", is_active=True
        )
        product = WholesaleProduct.objects.create(
            wholesaler=profile,
            category=cat,
            title="Draft",
            slug="p3-draft",
            sku="P3-D",
            short_description="x",
            description="x",
            moq=1,
            base_price=Decimal("10"),
            suggested_retail_price=Decimal("20"),
            approval_status="DRAFT",
        )
        resp = self.client.post(
            reverse("distributors:cross_sell_order", args=[product.pk]),
            {
                "buyer_name": "B",
                "buyer_email": "b@example.com",
                "buyer_phone": "9898000302",
                "delivery_city": "A",
                "delivery_pincode": "380015",
                "requested_quantity": 1,
                "expected_purchase_timeline": "Immediate (Within 7 days)",
                "message": "hi",
            },
        )
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(BuyerInquiry.objects.exists())

    def test_invite_message_error_hides_exception_text(self):
        with patch("apps.admin_panel.models.User.objects") as objs:
            objs.filter.side_effect = RuntimeError("SECRET-DB-DETAIL")
            resp = self.client.post(
                reverse("distributors:dashboard_invite_message"),
                "{}",
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("SECRET-DB-DETAIL", resp.content.decode())
