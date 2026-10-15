"""
Django Admin Configuration for Wholesale Models.
"""
from django.contrib import admin
from apps.wholesale.models.profile import WholesalerProfile, BusinessVerificationDocument
from apps.wholesale.models.category import ProductCategory
from apps.wholesale.models.product import WholesaleProduct, ProductImage, ProductVariant
from apps.wholesale.models.pricing import WholesalePriceTier
from apps.wholesale.models.approval import ProductApprovalLog
from apps.wholesale.models.relationship import ProductRelationship
from apps.wholesale.models.inquiry import BuyerInquiry, InquiryMessage
from apps.wholesale.models.import_job import BulkImportJob, BulkImportError

class VerificationDocumentInline(admin.TabularInline):
    model = BusinessVerificationDocument
    extra = 0

@admin.register(WholesalerProfile)
class WholesalerProfileAdmin(admin.ModelAdmin):
    list_display = ['business_name', 'contact_person', 'city', 'state', 'verification_status', 'created_at']
    list_filter = ['verification_status', 'business_type', 'state']
    search_fields = ['business_name', 'contact_person', 'email', 'phone', 'gstin']
    inlines = [VerificationDocumentInline]

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

class WholesalePriceTierInline(admin.TabularInline):
    model = WholesalePriceTier
    extra = 1

class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1

@admin.register(WholesaleProduct)
class WholesaleProductAdmin(admin.ModelAdmin):
    list_display = ['title', 'sku', 'wholesaler', 'category', 'base_price', 'moq', 'stock_quantity', 'approval_status', 'is_featured']
    list_filter = ['approval_status', 'is_featured', 'category', 'condition']
    search_fields = ['title', 'sku', 'brand', 'wholesaler__business_name']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ProductImageInline, WholesalePriceTierInline, ProductVariantInline]

@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'parent', 'is_active', 'sort_order']
    list_filter = ['is_active', 'parent']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(BuyerInquiry)
class BuyerInquiryAdmin(admin.ModelAdmin):
    list_display = ['id', 'product', 'wholesaler', 'buyer_name', 'requested_quantity', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['buyer_name', 'buyer_email', 'buyer_phone', 'product__title']

admin.site.register(ProductApprovalLog)
admin.site.register(ProductRelationship)
admin.site.register(BulkImportJob)
