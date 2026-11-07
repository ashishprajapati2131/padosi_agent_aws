"""Admin routes served by views/delete.py."""
from django.urls import path

from ..views.delete import admin_delete

urlpatterns = [
    path("admin/delete/", admin_delete, name="admin_agents_delete"),
]
