"""Admin routes served by views/insurance_approvals.py."""
from django.urls import path

from ..views.insurance_approvals import (
    insurance_approvals_index,
    insurance_approvals_process,
    insurance_approvals_approve_onboarding,
    insurance_approvals_reject_onboarding,
)

urlpatterns = [
    path("admin/insurance-approvals/", insurance_approvals_index, name="admin_insurance_approvals_index"),
    path("admin/insurance-approvals/<int:id>/process/", insurance_approvals_process, name="admin_insurance_approvals_process"),
    path("admin/insurance-approvals/onboarding/<int:id>/approve/", insurance_approvals_approve_onboarding, name="admin_insurance_approvals_approve_onboarding"),
    path("admin/insurance-approvals/onboarding/<int:id>/reject/", insurance_approvals_reject_onboarding, name="admin_insurance_approvals_reject_onboarding"),
]
