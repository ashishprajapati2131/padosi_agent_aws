"""Admin routes served by views/events.py."""
from django.urls import path

from ..views.events import event_list, event_show, event_export

urlpatterns = [
    path("admin/events/", event_list, name="admin_events_index"),
    path("admin/events/<int:event_id>/", event_show, name="admin_events_show"),
    path("admin/events/<int:event_id>/export/", event_export, name="admin_events_export"),
]
