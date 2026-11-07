"""Admin routes served by views/broadcast.py."""
from django.urls import path

from ..views.broadcast import broadcast_index, send_broadcast

urlpatterns = [
    path("admin/broadcast/",                broadcast_index,           name="broadcast_index"),
    path("admin/broadcast/send/",           send_broadcast,            name="broadcast_send"),
]
