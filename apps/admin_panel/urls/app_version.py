"""Admin routes served by views/app_version.py."""
from django.urls import path

from ..views.app_version import app_version_index, app_version_save

urlpatterns = [
    path("admin/app-version/", app_version_index, name="admin_app_version"),
    path("admin/app-version/save/", app_version_save, name="admin_app_version_save"),
]
