"""
Wholesaler Profile and Business Verification Models.
"""
from django.db import models
from django.conf import settings
from datetime import datetime

class WholesalerProfile(models.Model):
    """Business entity profile for wholesale vendors/manufacturers."""
    
    BUSINESS_TYPE_CHOICES = [
        ('MANUFACTURER', 'Manufacturer'),
        ('WHOLESALER', 'Wholesaler / Stockist'),
        ('TRADER', 'Trader / Merchant'),
        ('DISTRIBUTOR', 'Distributor / Super Stockist'),
        ('IMPORTER', 'Importer'),
    ]
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted for Verification'),
        ('UNDER_REVIEW', 'Under Review'),
        ('INFO_REQUIRED', 'Additional Information Required'),
        ('APPROVED', 'Approved / Verified'),
        ('REJECTED', 'Rejected'),
        ('SUSPENDED', 'Suspended'),
    ]
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wholesaler_profile'
    )
    
    # Business Identity
    business_name = models.CharField(max_length=255, db_index=True)
    business_type = models.CharField(max_length=30, choices=BUSINESS_TYPE_CHOICES, default='WHOLESALER')
    contact_person = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(max_length=254, db_index=True)
    website = models.URLField(blank=True, null=True)
    description = models.TextField(blank=True, null=True, help_text="Brief company overview and capabilities")
    
    # Address & Location
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=100, db_index=True)
    pincode = models.CharField(max_length=15, db_index=True)
    country = models.CharField(max_length=100, default='India')
    
    # Compliance & Legal
    gstin = models.CharField(max_length=20, blank=True, null=True, db_index=True, help_text="15-character GSTIN")
    pan_number = models.CharField(max_length=15, blank=True, null=True, help_text="Company/Proprietor PAN")
    business_registration_no = models.CharField(max_length=60, blank=True, null=True, help_text="MSME / CIN / Shop Act")
    
    # Verification State
    verification_status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='DRAFT', db_index=True)
    admin_notes = models.TextField(blank=True, null=True, help_text="Internal notes visible only to admins")
    rejection_reason = models.TextField(blank=True, null=True, help_text="Reason provided to seller upon rejection")
    
    verified_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=datetime.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ws_wholesaler_profiles'
        verbose_name = 'Wholesaler Profile'
        verbose_name_plural = 'Wholesaler Profiles'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.business_name} ({self.get_verification_status_display()})"
    
    @property
    def is_verified(self):
        return self.verification_status == 'APPROVED'

    @property
    def company_name(self):
        return self.business_name

    @property
    def can_publish_products(self):
        """Only approved wholesalers may have published products."""
        return self.verification_status == 'APPROVED'


class BusinessVerificationDocument(models.Model):
    """KYC and business proof documents submitted by wholesalers."""
    
    DOC_TYPE_CHOICES = [
        ('GST_CERT', 'GST Registration Certificate'),
        ('BUSINESS_REG', 'Udyam / MSME / Certificate of Incorporation'),
        ('PAN_CARD', 'Business PAN Card'),
        ('CANCELLED_CHEQUE', 'Cancelled Cheque / Bank Statement'),
        ('OTHER', 'Other Official Proof'),
    ]
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending Verification'),
        ('APPROVED', 'Verified & Accepted'),
        ('REJECTED', 'Rejected'),
    ]
    
    wholesaler = models.ForeignKey(
        WholesalerProfile,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    document_type = models.CharField(max_length=30, choices=DOC_TYPE_CHOICES)
    document_file = models.FileField(upload_to='wholesale/documents/%Y/%m/')
    document_number = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    rejection_notes = models.TextField(blank=True, null=True)
    
    uploaded_at = models.DateTimeField(default=datetime.now)
    verified_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'ws_verification_documents'
        verbose_name = 'Verification Document'
        verbose_name_plural = 'Verification Documents'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.wholesaler.business_name} ({self.get_status_display()})"
