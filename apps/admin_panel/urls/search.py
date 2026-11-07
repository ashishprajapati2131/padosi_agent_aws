"""Admin routes served by views/search.py."""
from django.urls import path

from apps.admin_panel.views.search import admin_search

urlpatterns = [
    path("admin/search/", admin_search, name="admin_search"),
]
