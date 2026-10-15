"""
Consolidated URL routes for apps.wholesale.
Includes Public Catalog, Wholesaler Portal, Admin Approvals, Feature Flag, and REST APIs.
"""
from django.urls import path, include
from apps.wholesale.views import (
    auth_views,
    public_views,
    wholesaler_views,
    admin_views,
    rfq_views,
)

app_name = 'wholesale'

urlpatterns = [
    # ── Public Marketplace ──────────────────────────────────────────────────
    path('', public_views.catalog_view, name='catalog'),
    path('product/<slug:slug>/', public_views.product_detail_view, name='product_detail'),
    path('product/<int:product_id>/calculate-price/', public_views.calculate_price_api, name='calculate_price_api'),
    path('product/<int:product_id>/rfq/', rfq_views.submit_rfq_view, name='submit_rfq'),

    # ── Wholesaler Portal & Auth ────────────────────────────────────────────
    path('wholesaler/login/', auth_views.wholesaler_login_view, name='wholesaler_login'),
    path('wholesaler/logout/', auth_views.wholesaler_logout_view, name='wholesaler_logout'),
    path('wholesaler/register/', auth_views.wholesaler_register_view, name='wholesaler_register'),
    path('wholesaler/dashboard/', wholesaler_views.wholesaler_dashboard_view, name='wholesaler_dashboard'),
    path('wholesaler/products/', wholesaler_views.wholesaler_product_list_view, name='wholesaler_products'),
    path('wholesaler/products/new/', wholesaler_views.product_wizard_view, name='product_create'),
    path('wholesaler/products/<int:product_id>/edit/', wholesaler_views.product_wizard_view, name='product_edit'),
    path('wholesaler/products/<int:product_id>/toggle/', wholesaler_views.product_status_toggle_view, name='product_toggle'),
    path('wholesaler/bulk-upload/', wholesaler_views.bulk_upload_view, name='bulk_upload'),
    path('wholesaler/inquiries/', wholesaler_views.wholesaler_inquiries_view, name='wholesaler_inquiries'),
    path('wholesaler/inquiries/<int:inquiry_id>/reply/', rfq_views.rfq_reply_view, name='rfq_reply'),

    # ── Wholesale Administrator Portal ──────────────────────────────────────
    path('admin/dashboard/', admin_views.admin_dashboard_view, name='admin_dashboard'),
    path('admin/approvals/', admin_views.admin_approval_queue_view, name='admin_approval_queue'),
    path('admin/approvals/queue/', admin_views.admin_approval_queue_view, name='admin_approvals'),
    path('admin/approvals/<int:product_id>/', admin_views.admin_review_product_view, name='admin_review_product'),
    path('admin/wholesalers/<int:wholesaler_id>/verify/', admin_views.admin_verify_wholesaler_view, name='admin_verify_wholesaler'),
    path('admin/categories/', admin_views.admin_categories_view, name='admin_categories'),
    path('admin/cross-sell/', admin_views.admin_cross_sell_view, name='admin_cross_sell'),
    path('admin/feature-flag/toggle/', admin_views.admin_toggle_feature_flag_view, name='admin_toggle_feature_flag'),

    # ── REST API ────────────────────────────────────────────────────────────
    path('api/v1/', include('apps.wholesale.api.urls')),
]
