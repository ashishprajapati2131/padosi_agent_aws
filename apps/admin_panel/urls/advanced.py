"""Admin routes served by views/advanced.py."""
from django.urls import path

from ..views.advanced import analytics, activity_logs, delete_activity_log

urlpatterns = [
    path("admin/advanced/analytics/",       analytics,                 name="advanced_analytics"),
    path("admin/advanced/activity-logs/",   activity_logs,             name="advanced_activity_logs"),
    path("admin/advanced/activity-logs/delete/", delete_activity_log,  name="advanced_activity_logs_delete"),
]
