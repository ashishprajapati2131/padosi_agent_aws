"""
Seed script to create initial wholesale categories, sample wholesalers, products, tiers, and cross-sell links.
Tailored for PadosiAgent B2B Supplies & Wholesale Marketplace.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import datetime
from apps.wholesale.models.category import ProductCategory
from apps.wholesale.models.profile import WholesalerProfile
from apps.wholesale.models.product import WholesaleProduct, ProductVariant
from apps.wholesale.models.pricing import WholesalePriceTier
from apps.wholesale.models.relationship import ProductRelationship

class Command(BaseCommand):
    help = 'Seeds initial wholesale categories, sellers, products, and price tiers for PadosiAgent'

    def handle(self, *args, **options):
        self.stdout.write("Seeding wholesale marketplace data...")

        # 1. Categories
        cat_stationery, _ = ProductCategory.objects.get_or_create(
            slug='office-stationery',
            defaults={
                'name': 'Office & Agency Stationery',
                'icon_class': 'fa-solid fa-folder-open',
                'description': 'Policy presentation folders, document organizers, certificates and office stationery supplies'
            }
        )
        cat_marketing, _ = ProductCategory.objects.get_or_create(
            slug='marketing-merchandise',
            defaults={
                'name': 'Marketing & Promotional Merchandise',
                'icon_class': 'fa-solid fa-bullhorn',
                'description': 'Custom engraved metal pens, branded umbrellas, keychains, and client promotional giveaways'
            }
        )
        cat_gifting, _ = ProductCategory.objects.get_or_create(
            slug='client-gifting',
            defaults={
                'name': 'Client Gifting & Hampers',
                'icon_class': 'fa-solid fa-gift',
                'description': 'Corporate gift hampers, premium desk organizers, insulated flask sets for policyholders'
            }
        )
        cat_medical, _ = ProductCategory.objects.get_or_create(
            slug='health-medical-devices',
            defaults={
                'name': 'Health & Medical Checkup Devices',
                'icon_class': 'fa-solid fa-heart-pulse',
                'description': 'Digital BP monitors, pulse oximeters, and diagnostic kits for agent health camps'
            }
        )

        # 2. Wholesalers
        # Seller 1: Swastik Stationery & Print Works
        u_swastik, _ = User.objects.get_or_create(
            username='swastik_supplies',
            defaults={'email': 'sales@swastikstationery.in', 'first_name': 'Ramesh Shah'}
        )
        u_swastik.set_password('WholesalePass123!')
        u_swastik.save()

        swastik_profile, _ = WholesalerProfile.objects.get_or_create(
            user=u_swastik,
            defaults={
                'business_name': 'Swastik Premium Print & Stationery LLP',
                'business_type': 'MANUFACTURER',
                'contact_person': 'Ramesh Shah',
                'phone': '9876543210',
                'email': 'sales@swastikstationery.in',
                'city': 'Ahmedabad',
                'state': 'Gujarat',
                'pincode': '380001',
                'gstin': '24AAACS1234A1Z5',
                'verification_status': 'APPROVED',
                'verified_at': datetime.now(),
                'description': 'Manufacturer of premium gold-embossed leatherette policy presentation folders, certificate covers, and customized agency kits.'
            }
        )

        # Seller 2: PrimePromo Branded Merchandise
        u_prime, _ = User.objects.get_or_create(
            username='prime_promo',
            defaults={'email': 'orders@primepromotions.in', 'first_name': 'Vikram Mehra'}
        )
        u_prime.set_password('PrimePass123!')
        u_prime.save()

        prime_profile, _ = WholesalerProfile.objects.get_or_create(
            user=u_prime,
            defaults={
                'business_name': 'PrimePromo Corporate Merchandise Ltd',
                'business_type': 'DISTRIBUTOR',
                'contact_person': 'Vikram Mehra',
                'phone': '9825012345',
                'email': 'orders@primepromotions.in',
                'city': 'Surat',
                'state': 'Gujarat',
                'pincode': '395007',
                'gstin': '24BBBCP5678B1Z2',
                'verification_status': 'APPROVED',
                'verified_at': datetime.now(),
                'description': 'Direct distributor for custom corporate laser-engraved executive pens, stainless flasks, and agent promotional kits across India.'
            }
        )

        # Seller 3: MediCare Diagnostic Wholesale
        u_medicare, _ = User.objects.get_or_create(
            username='medicare_wholesale',
            defaults={'email': 'care@medicaredevices.in', 'first_name': 'Dr. Sunita Rao'}
        )
        u_medicare.set_password('MediPass123!')
        u_medicare.save()

        medicare_profile, _ = WholesalerProfile.objects.get_or_create(
            user=u_medicare,
            defaults={
                'business_name': 'MediCare Health Supplies Pvt Ltd',
                'business_type': 'IMPORTER',
                'contact_person': 'Dr. Sunita Rao',
                'phone': '9811122233',
                'email': 'care@medicaredevices.in',
                'city': 'Mumbai',
                'state': 'Maharashtra',
                'pincode': '400001',
                'gstin': '27AAACM9999M1Z9',
                'verification_status': 'APPROVED',
                'verified_at': datetime.now(),
                'description': 'Importer and bulk supplier of certified digital health monitoring devices used by insurance agents during medical underwriting camps.'
            }
        )

        # 3. Products
        # Product 1: Policy Folder
        p_folder, _ = WholesaleProduct.objects.get_or_create(
            sku='KIT-POL-FOLD-01',
            wholesaler=swastik_profile,
            defaults={
                'title': 'Premium Leatherette Policy Presentation Folder (Navy Gold)',
                'category': cat_stationery,
                'brand': 'Padosi Stationery Pro',
                'condition': 'NEW',
                'base_price': Decimal('220.00'),
                'suggested_retail_price': Decimal('350.00'),
                'moq': 25,
                'stock_quantity': 1500,
                'unit_of_measure': 'Piece',
                'short_description': 'Deluxe navy-blue policy delivery folder with metallic gold embossing and clear document pockets.',
                'description': 'Designed specifically for life and health insurance advisors. High durability waterproof PU leatherette with dual inside document sleeves, business card pocket, and magnetic closure flap.',
                'approval_status': 'PUBLISHED',
                'is_featured': True,
                'view_count': 342,
                'inquiry_count': 28
            }
        )
        WholesalePriceTier.objects.get_or_create(product=p_folder, min_quantity=25, defaults={'max_quantity': 49, 'unit_price': Decimal('210.00')})
        WholesalePriceTier.objects.get_or_create(product=p_folder, min_quantity=50, defaults={'max_quantity': 99, 'unit_price': Decimal('185.00')})
        WholesalePriceTier.objects.get_or_create(product=p_folder, min_quantity=100, defaults={'max_quantity': None, 'unit_price': Decimal('160.00')})

        # Product 2: Executive Pen
        p_pen, _ = WholesaleProduct.objects.get_or_create(
            sku='MKT-PEN-ENG-02',
            wholesaler=prime_profile,
            defaults={
                'title': 'Executive Metal Rollerball Pen with Custom Agency Engraving',
                'category': cat_marketing,
                'brand': 'SignaCraft',
                'condition': 'NEW',
                'base_price': Decimal('95.00'),
                'suggested_retail_price': Decimal('175.00'),
                'moq': 50,
                'stock_quantity': 5000,
                'unit_of_measure': 'Piece',
                'short_description': 'Heavyweight matte black metal pen with personalized laser engraving of your Agency name & mobile number.',
                'description': 'Deliver memorable client consultations. High quality 0.5mm German liquid ink rollerball refill, twist mechanism, durable brass barrel, and scratch-resistant matte black coating.',
                'approval_status': 'PUBLISHED',
                'is_featured': True,
                'view_count': 518,
                'inquiry_count': 42
            }
        )
        WholesalePriceTier.objects.get_or_create(product=p_pen, min_quantity=50, defaults={'max_quantity': 99, 'unit_price': Decimal('88.00')})
        WholesalePriceTier.objects.get_or_create(product=p_pen, min_quantity=100, defaults={'max_quantity': 249, 'unit_price': Decimal('75.00')})
        WholesalePriceTier.objects.get_or_create(product=p_pen, min_quantity=250, defaults={'max_quantity': None, 'unit_price': Decimal('62.00')})

        # Product 3: Client Hamper
        p_hamper, _ = WholesaleProduct.objects.get_or_create(
            sku='GIFT-INS-HAMP-03',
            wholesaler=prime_profile,
            defaults={
                'title': 'Executive Client Welcome Gift Hamper (Flask, Pen & Diary)',
                'category': cat_gifting,
                'brand': 'Regal Box',
                'condition': 'NEW',
                'base_price': Decimal('550.00'),
                'suggested_retail_price': Decimal('899.00'),
                'moq': 20,
                'stock_quantity': 800,
                'unit_of_measure': 'Box',
                'short_description': 'Luxury 3-piece corporate welcome gift box with vacuum insulated thermos flask, metal pen, and A5 executive planner.',
                'description': 'The ultimate token of appreciation for high-value clients and family policy closures. Packaged in a magnetic rigid gift box with satin ribbon.',
                'approval_status': 'PUBLISHED',
                'is_featured': True,
                'view_count': 285,
                'inquiry_count': 19
            }
        )
        WholesalePriceTier.objects.get_or_create(product=p_hamper, min_quantity=20, defaults={'max_quantity': 49, 'unit_price': Decimal('520.00')})
        WholesalePriceTier.objects.get_or_create(product=p_hamper, min_quantity=50, defaults={'max_quantity': None, 'unit_price': Decimal('470.00')})

        # Product 4: Digital BP Monitor
        p_bp, _ = WholesaleProduct.objects.get_or_create(
            sku='MED-BP-AUTO-04',
            wholesaler=medicare_profile,
            defaults={
                'title': 'Automatic Digital Blood Pressure Monitor with Large LCD',
                'category': cat_medical,
                'brand': 'AccuCheck Medical',
                'condition': 'NEW',
                'base_price': Decimal('850.00'),
                'suggested_retail_price': Decimal('1499.00'),
                'moq': 10,
                'stock_quantity': 650,
                'unit_of_measure': 'Piece',
                'short_description': 'Clinically validated upper arm blood pressure measurement device with voice readout and 2x99 reading memory.',
                'description': 'Ideal for agents organizing free neighbourhood health camps or gifting to elderly clients. USB rechargeable and standard AA battery support with 2-year warranty.',
                'approval_status': 'PUBLISHED',
                'is_featured': True,
                'view_count': 194,
                'inquiry_count': 14
            }
        )
        WholesalePriceTier.objects.get_or_create(product=p_bp, min_quantity=10, defaults={'max_quantity': 24, 'unit_price': Decimal('810.00')})
        WholesalePriceTier.objects.get_or_create(product=p_bp, min_quantity=25, defaults={'max_quantity': None, 'unit_price': Decimal('740.00')})

        # 4. Cross-Sell Pairings
        ProductRelationship.objects.get_or_create(
            source_product=p_folder,
            target_product=p_pen,
            relationship_type='COMPLEMENTARY',
            defaults={'display_order': 1}
        )
        ProductRelationship.objects.get_or_create(
            source_product=p_folder,
            target_product=p_hamper,
            relationship_type='RELATED',
            defaults={'display_order': 2}
        )

        self.stdout.write(self.style.SUCCESS("Wholesale seed data initialized successfully!"))
