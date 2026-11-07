"""Admin routes served by views/insurance.py."""
from django.urls import path

from ..views.insurance import (
    insurance_index,
    insurance_create,
    insurance_store,
    insurance_show,
    insurance_toggle_status,
)

urlpatterns = [
    path("admin/insurance/", insurance_index, name="admin_insurance_index"),
    path("admin/insurance/create/", insurance_create, name="admin_insurance_create"),
    path("admin/insurance/store/", insurance_store, name="admin_insurance_store"),
    path("admin/insurance/<int:id>/", insurance_show, name="admin_insurance_show"),
    path("admin/insurance/toggle-status/", insurance_toggle_status, name="admin_insurance_toggle_status"),
]
