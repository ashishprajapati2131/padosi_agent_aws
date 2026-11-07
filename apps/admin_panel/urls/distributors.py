"""Admin routes served by views/distributors.py."""
from django.urls import path

from ..views.distributors import (
    distributor_list,
    distributor_create,
    distributor_store,
    toggle_distributor_status,
    distributor_reset_password,
    subdistributor_reset_password,
    distributor_detail,
)

urlpatterns = [
    path("admin/distributors/", distributor_list, name="admin_distributors"),
    path("admin/distributors/create/", distributor_create, name="admin_distributors_create"),
    path("admin/distributors/store/", distributor_store, name="admin_distributors_store"),
    path("admin/distributors/toggle-status/", toggle_distributor_status, name="admin_distributor_toggle_status"),
    path("admin/distributors/reset-password/", distributor_reset_password, name="admin_distributor_reset_password"),
    path("admin/distributors/sub/reset-password/", subdistributor_reset_password, name="admin_subdistributor_reset_password"),
    path("admin/distributors/<int:distributor_id>/", distributor_detail, name="admin_distributor_detail"),
]
