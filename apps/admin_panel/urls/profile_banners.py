"""Admin routes served by views/profile_banners.py."""
from django.urls import path

from ..views.profile_banners import (
    profile_banners_index,
    profile_banner_upload,
    profile_banner_toggle,
    profile_banner_delete,
    profile_banner_settings_save,
)

urlpatterns = [
    path("admin/profile-banners/", profile_banners_index, name="admin_profile_banners_index"),
    path("admin/profile-banners/upload/", profile_banner_upload, name="admin_profile_banner_upload"),
    path("admin/profile-banners/<int:banner_id>/toggle/", profile_banner_toggle, name="admin_profile_banner_toggle"),
    path("admin/profile-banners/<int:banner_id>/delete/", profile_banner_delete, name="admin_profile_banner_delete"),
    path("admin/profile-banners/settings/save/", profile_banner_settings_save, name="admin_profile_banner_settings_save"),
]
