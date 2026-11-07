"""Admin routes served by views/error_logs.py."""
from django.urls import path

from apps.admin_panel.views.error_logs import error_logs_index, error_logs_show, error_logs_delete

urlpatterns = [
    path("admin/advanced/error-logs/", error_logs_index, name="admin_error_logs_index"),
    path("admin/advanced/error-logs/<int:id>/", error_logs_show, name="admin_error_logs_show"),
    path("admin/advanced/error-logs/delete/", error_logs_delete, name="admin_error_logs_delete"),
]
