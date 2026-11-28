"""Admin routes for the privacy policy shown at /privacy/."""
from django.urls import path

from ..views.privacy_policy import (
    privacy_create,
    privacy_delete,
    privacy_edit,
    privacy_index,
    privacy_publish,
    privacy_store,
    privacy_update,
)

urlpatterns = [
    path("admin/privacy-policy/", privacy_index, name="admin_privacy_policies"),
    path("admin/privacy-policy/create/", privacy_create, name="admin_privacy_policy_create"),
    path("admin/privacy-policy/store/", privacy_store, name="admin_privacy_policy_store"),
    path("admin/privacy-policy/<int:policy_id>/publish/", privacy_publish, name="admin_privacy_policy_publish"),
    path("admin/privacy-policy/<int:policy_id>/edit/", privacy_edit, name="admin_privacy_policy_edit"),
    path("admin/privacy-policy/<int:policy_id>/update/", privacy_update, name="admin_privacy_policy_update"),
    path("admin/privacy-policy/<int:policy_id>/delete/", privacy_delete, name="admin_privacy_policy_delete"),
]
