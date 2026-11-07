"""Admin routes served by views/subscriptions.py."""
from django.urls import path

from ..views import subscriptions

urlpatterns = [
    path("admin/subscriptions/",            subscriptions.subscriptions_index, name="admin_subscriptions_index"),
    path("admin/subscriptions/delete/",     subscriptions.delete_subscription, name="admin_delete_subscription"),
]
