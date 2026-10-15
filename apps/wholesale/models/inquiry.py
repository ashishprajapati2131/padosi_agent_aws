"""
Buyer Inquiry and Request for Quotation (RFQ) Models.
"""
from django.db import models
from django.conf import settings
from datetime import datetime
from .product import WholesaleProduct, ProductVariant
from .profile import WholesalerProfile

class BuyerInquiry(models.Model):
    """Quotation request or inquiry submitted by a buyer on a product."""
    
    STATUS_CHOICES = [
        ('NEW', 'New Inquiry'),
        ('OPEN', 'Open / Under Discussion'),
        ('SELLER_REPLIED', 'Seller Replied'),
        ('QUOTATION_SENT', 'Quotation Sent'),
        ('NEGOTIATION', 'Negotiating Terms'),
        ('CONVERTED', 'Converted to Order'),
        ('CLOSED', 'Closed'),
        ('SPAM', 'Flagged as Spam'),
    ]
    
    product = models.ForeignKey(
        WholesaleProduct,
        on_delete=models.CASCADE,
        related_name='inquiries',
        db_index=True
    )
    wholesaler = models.ForeignKey(
        WholesalerProfile,
        on_delete=models.CASCADE,
        related_name='inquiries_received',
        db_index=True
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inquiries'
    )
    buyer_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='wholesale_inquiries'
    )
    
    # Buyer Contact Details
    buyer_name = models.CharField(max_length=150)
    buyer_email = models.EmailField(max_length=254)
    buyer_phone = models.CharField(max_length=25)
    company_name = models.CharField(max_length=200, blank=True, null=True)
    delivery_pincode = models.CharField(max_length=20)
    delivery_city = models.CharField(max_length=100)
    
    # Requirement Details
    requested_quantity = models.PositiveIntegerField(help_text="Units required")
    target_price_per_unit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expected_purchase_timeline = models.CharField(
        max_length=100,
        default='Immediate (Within 7 days)',
        help_text="Immediate, Within 15 days, 1 month, Regular monthly supply"
    )
    message = models.TextField(help_text="Customization, delivery terms, sample request, or questions")
    
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='NEW', db_index=True)
    seller_quotation_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    seller_notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(default=datetime.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ws_buyer_inquiries'
        verbose_name = 'Buyer Inquiry'
        verbose_name_plural = 'Buyer Inquiries'
        ordering = ['-created_at']

    def __str__(self):
        return f"RFQ #{self.id} for {self.product.title} from {self.buyer_name} ({self.requested_quantity} units)"


class InquiryMessage(models.Model):
    """Conversation thread messages within an inquiry."""
    
    SENDER_ROLE_CHOICES = [
        ('BUYER', 'Buyer'),
        ('SELLER', 'Seller / Wholesaler'),
        ('ADMIN', 'Platform Admin'),
    ]
    
    inquiry = models.ForeignKey(
        BuyerInquiry,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender_name = models.CharField(max_length=150)
    sender_role = models.CharField(max_length=20, choices=SENDER_ROLE_CHOICES, default='BUYER')
    message = models.TextField()
    attachment = models.FileField(upload_to='wholesale/rfq_attachments/%Y/%m/', blank=True, null=True)
    created_at = models.DateTimeField(default=datetime.now)

    class Meta:
        db_table = 'ws_inquiry_messages'
        verbose_name = 'Inquiry Message'
        verbose_name_plural = 'Inquiry Messages'
        ordering = ['created_at']

    def __str__(self):
        return f"Message by {self.sender_name} on RFQ #{self.inquiry_id}"
