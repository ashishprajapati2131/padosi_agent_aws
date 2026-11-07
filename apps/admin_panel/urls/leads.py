"""Admin routes served by views/leads.py."""
from django.urls import path

from ..views.leads import lead_list, update_lead_status

urlpatterns = [
    path("admin/leads/", lead_list, name="admin_leads_index"),
    path("admin/leads/update-status/", update_lead_status, name="admin_leads_update_status"),
]
