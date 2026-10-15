"""
Wholesale Product, Media, and Variant Models.
"""
from django.db import models
from django.utils.text import slugify
from datetime import datetime
from decimal import Decimal
from .profile import WholesalerProfile
from .category import ProductCategory

class WholesaleProduct(models.Model):
    """Core product listing for the wholesale marketplace."""
    
    CONDITION_CHOICES = [
        ('NEW', 'Brand New'),
        ('REFURBISHED', 'Refurbished / Certified'),
        ('SURPLUS', 'Overstock / Surplus Inventory'),
    ]
    
    APPROVAL_STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted for Approval'),
        ('UNDER_REVIEW', 'Under Review'),
        ('CHANGES_REQUESTED', 'Changes Requested'),
        ('APPROVED', 'Approved'),
        ('PUBLISHED', 'Published & Live'),
        ('REJECTED', 'Rejected'),
        ('PAUSED', 'Paused by Seller'),
        ('ARCHIVED', 'Archived'),
    ]
    
    wholesaler = models.ForeignKey(
        WholesalerProfile,
        on_delete=models.CASCADE,
        related_name='products',
        db_index=True
    )
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.PROTECT,
        related_name='products',
        db_index=True
    )
    
    # Basic Information
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=280, unique=True, db_index=True)
    sku = models.CharField(max_length=100, db_index=True, help_text="Seller specific SKU or Product Code")
    brand = models.CharField(max_length=150, blank=True, null=True, db_index=True)
    condition = models.CharField(max_length=30, choices=CONDITION_CHOICES, default='NEW')
    country_of_origin = models.CharField(max_length=100, default='India')
    tags = models.CharField(max_length=500, blank=True, null=True, help_text="Comma-separated keywords for search")
    
    short_description = models.CharField(max_length=500, help_text="Quick summary for card views and search")
    description = models.TextField(help_text="Detailed specifications, features, packaging info")
    
    # Commercial & Pricing
    base_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Base price per unit for minimum order quantity")
    suggested_retail_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Suggested Retail Price (MSRP)")
    currency = models.CharField(max_length=10, default='INR')
    tax_included = models.BooleanField(default=False, help_text="Whether base price includes applicable GST/taxes")
    tax_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'), help_text="Applicable GST %")
    
    moq = models.PositiveIntegerField(default=1, help_text="Minimum Order Quantity required to place order")
    max_order_quantity = models.PositiveIntegerField(null=True, blank=True)
    unit_of_measure = models.CharField(max_length=50, default='Piece', help_text="Piece, Box, Kg, Meter, Carton, Set")
    pack_size = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., '10 pieces per carton'")
    is_quote_only = models.BooleanField(default=False, help_text="If True, price is hidden and requires RFQ quote")
    
    # Inventory & Availability
    stock_quantity = models.PositiveIntegerField(default=0, help_text="Currently available ready-to-dispatch stock")
    low_stock_threshold = models.PositiveIntegerField(default=10)
    lead_time_days = models.PositiveIntegerField(default=3, help_text="Preparation time in business days")
    is_made_to_order = models.BooleanField(default=False)
    
    # Shipping & Fulfillment
    dispatch_location = models.CharField(max_length=150, default='Ahmedabad, Gujarat')
    shipping_regions = models.CharField(max_length=255, default='Pan India')
    shipping_charge_policy = models.CharField(max_length=150, default='Actual shipping charges at buyer account')
    local_pickup_available = models.BooleanField(default=True)
    
    # Business Terms & Specifications
    return_policy = models.CharField(max_length=255, default='Replacement only for manufacturing defects within 7 days')
    warranty_info = models.CharField(max_length=255, blank=True, null=True, default='1 Year Manufacturer Warranty')
    customization_available = models.BooleanField(default=False, help_text="OEM / Private label / Custom packaging available")
    sample_available = models.BooleanField(default=False, help_text="Paid or free samples can be dispatched")
    
    # Moderation & Approval Lifecycle
    approval_status = models.CharField(max_length=30, choices=APPROVAL_STATUS_CHOICES, default='DRAFT', db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    admin_feedback = models.TextField(blank=True, null=True, help_text="Actionable feedback for revision requests")
    rejection_reason = models.TextField(blank=True, null=True, help_text="Mandatory explanation if rejected")
    reviewed_by = models.CharField(max_length=150, blank=True, null=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    
    # Counters & Timestamps
    view_count = models.PositiveIntegerField(default=0)
    inquiry_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=datetime.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ws_products'
        verbose_name = 'Wholesale Product'
        verbose_name_plural = 'Wholesale Products'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.sku}) - {self.get_approval_status_display()}"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(f"{self.title}-{self.sku}")
            slug = base_slug
            counter = 1
            while WholesaleProduct.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_live(self):
        """Publicly visible only if product is published AND wholesaler is approved."""
        return self.approval_status == 'PUBLISHED' and self.wholesaler.is_verified

    @property
    def primary_image(self):
        primary = self.images.filter(is_primary=True).first()
        if not primary:
            primary = self.images.order_by('sort_order', 'id').first()
        return primary

    @property
    def formatted_base_price(self):
        return f"₹{self.base_price:,.2f}"

    @property
    def name(self):
        return self.title

    @property
    def base_wholesale_price(self):
        return self.base_price

    @property
    def retail_msrp(self):
        return self.suggested_retail_price

    @property
    def discount_percentage(self):
        if self.suggested_retail_price and self.suggested_retail_price > self.base_price:
            return round(((self.suggested_retail_price - self.base_price) / self.suggested_retail_price) * 100)
        return 0

    def get_price_for_quantity(self, quantity: int) -> Decimal:
        """
        Calculates unit price based on configured wholesale tiered pricing.
        Falls back to base_price if quantity is below or between tiers.
        """
        if quantity < self.moq:
            quantity = self.moq
            
        applicable_tier = self.price_tiers.filter(
            min_quantity__lte=quantity
        ).filter(
            models.Q(max_quantity__gte=quantity) | models.Q(max_quantity__isnull=True)
        ).order_by('-min_quantity').first()
        
        if applicable_tier:
            return applicable_tier.unit_price
        return self.base_price


class ProductImage(models.Model):
    """Product gallery images."""
    
    product = models.ForeignKey(
        WholesaleProduct,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(upload_to='wholesale/products/%Y/%m/')
    alt_text = models.CharField(max_length=255, blank=True, null=True)
    is_primary = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=datetime.now)

    class Meta:
        db_table = 'ws_product_images'
        verbose_name = 'Product Image'
        verbose_name_plural = 'Product Images'
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f"Image for {self.product.sku}"


class ProductVariant(models.Model):
    """Optional product variants (e.g. Size, Color, Packaging configuration)."""
    
    product = models.ForeignKey(
        WholesaleProduct,
        on_delete=models.CASCADE,
        related_name='variants'
    )
    name = models.CharField(max_length=150, help_text="e.g. Color: Blue, Size: XL, Pack: 100pcs")
    sku = models.CharField(max_length=100, db_index=True)
    price_delta = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text="Amount to add to base tier price")
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ws_product_variants'
        verbose_name = 'Product Variant'
        verbose_name_plural = 'Product Variants'
        unique_together = ('product', 'sku')

    def __str__(self):
        return f"{self.product.title} - {self.name} ({self.sku})"
