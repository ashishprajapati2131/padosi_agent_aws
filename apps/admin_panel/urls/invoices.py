"""Admin routes served by views/invoices.py."""
from django.urls import path

from ..views.invoices import (
    invoice_list,
    create_manual_invoice,
    admin_verify_promo,
    preview_invoice,
    download_invoice,
    save_sheet_url,
    sync_sheet,
    sync_single_invoice,
    open_sheet,
)

urlpatterns = [
    path("admin/invoices/", invoice_list, name="admin_invoices"),
    path("admin/invoices/create/", create_manual_invoice, name="admin_invoices_create"),
    path("admin/invoices/verify-promo/", admin_verify_promo, name="admin_invoices_verify_promo"),
    path("admin/invoices/<int:invoice_id>/preview/", preview_invoice, name="admin_invoice_preview"),
    path("admin/invoices/<int:invoice_id>/download/", download_invoice, name="admin_invoice_download"),
    path("admin/invoices/settings/url/", save_sheet_url, name="admin_invoice_save_sheet_url"),
    path("admin/invoices/sync/", sync_sheet, name="admin_invoice_sync_sheet"),
    path("admin/invoices/<int:invoice_id>/sync/", sync_single_invoice, name="admin_invoice_sync_single"),
    path("admin/invoices/open-sheet/", open_sheet, name="admin_invoice_open_sheet"),
]
