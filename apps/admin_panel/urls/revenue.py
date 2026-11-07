"""Admin routes served by views/revenue.py."""
from django.urls import path

from ..views.revenue import revenue_dashboard

urlpatterns = [
    path("admin/revenue/", revenue_dashboard, name="admin_revenue"),
]
