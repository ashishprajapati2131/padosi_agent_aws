"""Admin routes served by views/admins.py."""
from django.urls import path

from ..views.admins import (
    admins_index,
    admins_create,
    admins_store,
    admins_edit,
    admins_update,
    admins_destroy,
)

urlpatterns = [
    path("admin/admins/", admins_index, name="admin_admins_index"),
    path("admin/admins/create/", admins_create, name="admin_admins_create"),
    path("admin/admins/store/", admins_store, name="admin_admins_store"),
    path("admin/admins/<int:id>/edit/", admins_edit, name="admin_admins_edit"),
    path("admin/admins/<int:id>/update/", admins_update, name="admin_admins_update"),
    path("admin/admins/<int:id>/delete/", admins_destroy, name="admin_admins_delete"),
]
