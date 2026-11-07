"""Admin routes served by views/account_deletion.py."""
from django.urls import path

from ..views.account_deletion import (
    deletion_requests_list,
    terminate_agent_account,
    activate_agent_account,
    reject_deletion_request,
)

urlpatterns = [
    path("admin/account-deletion-requests/", deletion_requests_list, name="admin_deletion_requests"),
    path("admin/account-deletion/terminate/", terminate_agent_account, name="admin_terminate_account"),
    path("admin/account-deletion/activate/", activate_agent_account, name="admin_activate_account"),
    path("admin/account-deletion/reject/", reject_deletion_request, name="admin_reject_deletion_request"),
]
