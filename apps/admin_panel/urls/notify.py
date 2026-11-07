"""Admin routes served by views/notify.py."""
from django.urls import path

from ..views.notify import notify_index, notify_send, notify_broadcast

urlpatterns = [
    path("admin/agent/notifications/",             notify_index,              name="agent_notify"),
    path("admin/agent/notifications/send/",        notify_send,               name="agent_notify_send"),
    path("admin/agent/notifications/broadcast/",   notify_broadcast,          name="agent_notify_broadcast"),
]
