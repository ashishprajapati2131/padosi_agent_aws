"""Admin routes served by views/quick_registration_leads.py."""
from django.urls import path

from ..views.quick_registration_leads import (
    quick_registration_leads_list,
    quick_registration_lead_delete,
    quick_registration_leads_export_csv,
    quick_registration_leads_export_xlsx,
)

urlpatterns = [
    path("admin/quick-registration-leads/", quick_registration_leads_list, name="admin_quick_registration_leads"),
    path("admin/quick-registration-leads/<int:lead_id>/delete/", quick_registration_lead_delete, name="admin_quick_registration_lead_delete"),
    path("admin/quick-registration-leads/export/csv/", quick_registration_leads_export_csv, name="admin_quick_registration_leads_export_csv"),
    path("admin/quick-registration-leads/export/xlsx/", quick_registration_leads_export_xlsx, name="admin_quick_registration_leads_export_xlsx"),
]
