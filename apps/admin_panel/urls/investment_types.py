"""Admin routes served by views/investment_types.py."""
from django.urls import path

from apps.admin_panel.views.investment_types import (
    index as investment_types_index,
    store as investment_types_store,
    update as investment_types_update,
    delete as investment_types_delete,
    toggle_status as investment_types_toggle,
)

urlpatterns = [
    path("admin/investment-types/", investment_types_index, name="admin_investment_types_index"),
    path("admin/investment-types/store/", investment_types_store, name="admin_investment_types_store"),
    path("admin/investment-types/<int:pk>/update/", investment_types_update, name="admin_investment_types_update"),
    path("admin/investment-types/<int:pk>/delete/", investment_types_delete, name="admin_investment_types_delete"),
    path("admin/investment-types/<int:pk>/toggle/", investment_types_toggle, name="admin_investment_types_toggle"),
]
