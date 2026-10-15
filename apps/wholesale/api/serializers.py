"""
REST API Serializers for Wholesale System.
Compatible with DRF serializers.
"""
from rest_framework import serializers
from apps.wholesale.models.product import WholesaleProduct, ProductImage, ProductVariant
from apps.wholesale.models.pricing import WholesalePriceTier
from apps.wholesale.models.category import ProductCategory
from apps.wholesale.models.profile import WholesalerProfile
from apps.wholesale.models.inquiry import BuyerInquiry

class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ['id', 'name', 'slug', 'description', 'icon_class', 'parent']


class WholesalePriceTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = WholesalePriceTier
        fields = ['id', 'min_quantity', 'max_quantity', 'unit_price']


class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['id', 'image_url', 'is_primary', 'sort_order', 'alt_text']

    def get_image_url(self, obj):
        if obj.image:
            return obj.image.url
        return None


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ['id', 'name', 'sku', 'price_delta', 'stock_quantity', 'is_active']


class WholesalerPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = WholesalerProfile
        fields = ['id', 'business_name', 'business_type', 'city', 'state', 'verification_status', 'is_verified']


class WholesaleProductCatalogSerializer(serializers.ModelSerializer):
    wholesaler = WholesalerPublicSerializer(read_only=True)
    category = ProductCategorySerializer(read_only=True)
    primary_image_url = serializers.SerializerMethodField()
    price_tiers = WholesalePriceTierSerializer(many=True, read_only=True)

    class Meta:
        model = WholesaleProduct
        fields = [
            'id', 'title', 'slug', 'sku', 'brand', 'condition',
            'base_price', 'currency', 'tax_included', 'moq',
            'unit_of_measure', 'pack_size', 'stock_quantity',
            'lead_time_days', 'dispatch_location', 'wholesaler',
            'category', 'primary_image_url', 'price_tiers', 'is_featured'
        ]

    def get_primary_image_url(self, obj):
        img = obj.primary_image
        return img.image.url if img and img.image else None


class WholesaleProductDetailSerializer(WholesaleProductCatalogSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)

    class Meta(WholesaleProductCatalogSerializer.Meta):
        fields = WholesaleProductCatalogSerializer.Meta.fields + [
            'short_description', 'description', 'tax_rate_percent',
            'shipping_regions', 'shipping_charge_policy', 'return_policy',
            'warranty_info', 'customization_available', 'sample_available',
            'images', 'variants'
        ]


class BuyerInquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = BuyerInquiry
        fields = [
            'id', 'product', 'buyer_name', 'buyer_email', 'buyer_phone',
            'company_name', 'delivery_city', 'delivery_pincode',
            'requested_quantity', 'target_price_per_unit',
            'expected_purchase_timeline', 'message', 'status', 'created_at'
        ]
        read_only_fields = ['id', 'status', 'created_at']
