"""Admin routes served by views/agents_amfi.py."""
from django.urls import path

from ..views.agents_amfi import verify_amfi_arn

urlpatterns = [
    path("admin/agents/amfi-verify/", verify_amfi_arn, name="admin_agents_amfi_verify"),
]
