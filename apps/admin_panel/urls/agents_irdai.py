"""Admin routes served by views/agents_irdai.py."""
from django.urls import path

from ..views.agents_irdai import verify_irdai_license

urlpatterns = [
    path("admin/agents/irdai-verify/", verify_irdai_license, name="admin_agents_irdai_verify"),
]
