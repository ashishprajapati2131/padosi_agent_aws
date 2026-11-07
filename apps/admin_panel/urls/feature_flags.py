"""Admin routes served by views/feature_flags.py."""
from django.urls import path

from ..views.feature_flags import (
    feature_flags_index,
    feature_flag_toggle,
    feature_flag_create,
    feature_flag_update,
    feature_flag_delete,
)

urlpatterns = [
    path("admin/feature-flags/", feature_flags_index, name="admin_feature_flags"),
    path("admin/feature-flags/toggle/", feature_flag_toggle, name="admin_feature_flag_toggle"),
    path("admin/feature-flags/create/", feature_flag_create, name="admin_feature_flag_create"),
    path("admin/feature-flags/update/", feature_flag_update, name="admin_feature_flag_update"),
    path("admin/feature-flags/delete/", feature_flag_delete, name="admin_feature_flag_delete"),
]
