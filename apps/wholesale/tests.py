import json
from decimal import Decimal
from datetime import datetime, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.home.models.site_setting import SiteSetting
from apps.agents.models import Agent, AgentSubscription
from apps.wholesale.models.profile import WholesalerProfile
from apps.wholesale.models.category import ProductCategory
from apps.wholesale.models.product import WholesaleProduct
from apps.wholesale.models.pricing import WholesalePriceTier
from apps.wholesale.models.inquiry import BuyerInquiry

User = get_user_model()

class WholesaleSystemTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Ensure feature flag is enabled initially
        SiteSetting.set_value('wholesale_marketplace_enabled', '1', group='general')

        # Create Category
        self.category = ProductCategory.objects.create(
            name="Office Stationery & Documents",
            slug="office-stationery",
            is_active=True
        )

        # Create Wholesaler User & Profile
        self.wholesaler_user = User.objects.create_user(
            username="wholesaler_test",
            email="wholesaler_test@example.com",
            password="TestPassword123!"
        )
        self.wholesaler = WholesalerProfile.objects.create(
            user=self.wholesaler_user,
            business_name="Alpha Prints & Promo Hub",
            contact_person="Alok Verma",
            email="wholesaler_test@example.com",
            phone="9898000001",
            city="Ahmedabad",
            state="Gujarat",
            verification_status="APPROVED"
        )

        # Create Product
        self.product = WholesaleProduct.objects.create(
            wholesaler=self.wholesaler,
            category=self.category,
            title="Deluxe Leatherette Policy Document Folder",
            slug="deluxe-leatherette-policy-folder",
            sku="WS-FOLD-001",
            short_description="Executive stitched document folders with custom agent gold-foil stamping.",
            description="Detailed specifications for executive document folders.",
            moq=50,
            base_price=Decimal("120.00"),
            suggested_retail_price=Decimal("250.00"),
            approval_status="PUBLISHED",
            is_featured=True
        )

        # Create Price Tiers
        WholesalePriceTier.objects.create(
            product=self.product,
            min_quantity=50,
            max_quantity=199,
            unit_price=Decimal("120.00")
        )
        WholesalePriceTier.objects.create(
            product=self.product,
            min_quantity=200,
            max_quantity=499,
            unit_price=Decimal("95.00")
        )
        WholesalePriceTier.objects.create(
            product=self.product,
            min_quantity=500,
            max_quantity=None,
            unit_price=Decimal("80.00")
        )

        # Create Agent User & Profile
        self.agent_user = User.objects.create_user(
            username="agent_test",
            email="agent_test@example.com",
            password="AgentPassword123!"
        )
        self.agent = Agent.objects.create(
            user=self.agent_user,
            fullname="Rajesh Sharma",
            email="agent_test@example.com",
            mobile="9898123456",
            status="active",
            plan_type="professional",
            registration_step=2
        )
        
        # Create active completed subscription for agent to pass dashboard auth gate
        now = datetime.now()
        AgentSubscription.objects.create(
            agent=self.agent,
            payment_status='completed',
            status='active',
            selected_plan='professional',
            registration_amount=Decimal('4999.00'),
            razorpay_payment_id='pay_test1234567890',
            razorpay_order_id='order_test1234567890',
            starts_at=now,
            expires_at=now + timedelta(days=365)
        )

    def tearDown(self):
        SiteSetting.set_value('wholesale_marketplace_enabled', '1', group='general')

    def test_marketplace_catalog_view_when_enabled(self):
        """Public access is isolated: anonymous users are redirected to login, agents redirected to dashboard."""
        SiteSetting.set_value('wholesale_marketplace_enabled', '1', group='general')
        # Anonymous users should NOT see public marketplace
        response = self.client.get(reverse('wholesale:catalog'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/agent-login/', response.url)

        # Logged-in agent is directed to agent dashboard cross-sell tab
        self.client.force_login(self.agent_user)
        agent_resp = self.client.get(reverse('wholesale:catalog'))
        self.assertEqual(agent_resp.status_code, 302)
        self.assertEqual(agent_resp.url, '/agent/dashboard/?tab=marketplace')

    def test_feature_flag_disabled_renders_offline_notice(self):
        """When wholesale feature flag is OFF, wholesale routes return disabled notice."""
        SiteSetting.set_value('wholesale_marketplace_enabled', '0', group='general')
        
        response = self.client.get(reverse('wholesale:catalog'))
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "Wholesale Marketplace Inactive", status_code=503)

        # Product detail route should also be gated
        detail_response = self.client.get(reverse('wholesale:product_detail', kwargs={'slug': self.product.slug}))
        self.assertEqual(detail_response.status_code, 503)
        self.assertContains(detail_response, "Wholesale Marketplace Inactive", status_code=503)

    def test_product_detail_view_and_tiered_pricing(self):
        """Product detail page is private; authenticated agent views MOQ and tiered pricing."""
        SiteSetting.set_value('wholesale_marketplace_enabled', '1', group='general')
        # Anonymous is redirected
        anon_response = self.client.get(reverse('wholesale:product_detail', kwargs={'slug': self.product.slug}))
        self.assertEqual(anon_response.status_code, 302)

        # Authenticated agent can view details
        self.client.force_login(self.agent_user)
        response = self.client.get(reverse('wholesale:product_detail', kwargs={'slug': self.product.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Deluxe Leatherette Policy Document Folder")
        self.assertContains(response, "MOQ: 50")
        self.assertContains(response, "120.00")
        self.assertContains(response, "95.00")
        self.assertContains(response, "80.00")
        self.assertContains(response, "Request Wholesale Quotation")

    def test_agent_dashboard_marketplace_integration(self):
        """When agent visits dashboard, wholesale marketplace section & tab are present."""
        SiteSetting.set_value('wholesale_marketplace_enabled', '1', group='general')
        self.client.force_login(self.agent_user)
        
        response = self.client.get('/agent/dashboard/')
        self.assertEqual(response.status_code, 200)
        
        # Verify context
        self.assertTrue(response.context['wholesale_enabled'])
        self.assertTrue(len(response.context['wholesale_products']) > 0)
        
        # Verify HTML rendered content
        self.assertContains(response, "Deluxe Leatherette Policy Document Folder")

    def test_agent_dashboard_hides_wholesale_when_disabled(self):
        """When feature flag is OFF, wholesale products and tabs are hidden from agent dashboard."""
        SiteSetting.set_value('wholesale_marketplace_enabled', '0', group='general')
        self.client.force_login(self.agent_user)
        
        response = self.client.get('/agent/dashboard/')
        self.assertEqual(response.status_code, 200)
        
        self.assertFalse(response.context['wholesale_enabled'])
        self.assertEqual(len(response.context['wholesale_products']), 0)
        self.assertNotContains(response, "Agent Supplies &amp; B2B Marketplace")

    def test_rfq_inquiry_submission(self):
        """Agent can submit an RFQ / wholesale inquiry for a product."""
        post_data = {
            'buyer_name': 'Rajesh Sharma',
            'company_name': 'Sharma Insurance Advisory',
            'buyer_email': 'agent_test@example.com',
            'buyer_phone': '9898123456',
            'delivery_city': 'Ahmedabad',
            'delivery_pincode': '380015',
            'requested_quantity': 150,
            'target_price_per_unit': '100.00',
            'expected_purchase_timeline': 'Immediate (Within 7 days)',
            'message': 'Please provide sample with custom gold foil agency stamping.'
        }
        url = reverse('wholesale:submit_rfq', kwargs={'product_id': self.product.id})
        response = self.client.post(url, data=post_data)
        self.assertEqual(response.status_code, 302)
        
        inquiry = BuyerInquiry.objects.filter(product=self.product, buyer_email='agent_test@example.com').first()
        self.assertIsNotNone(inquiry)
        self.assertEqual(inquiry.requested_quantity, 150)
        self.assertEqual(inquiry.buyer_name, 'Rajesh Sharma')
