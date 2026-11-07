"""Admin routes served by views/plans.py."""
from django.urls import path

from ..views.plans import plans_index, plan_create, plan_edit, plan_delete

urlpatterns = [
    path("admin/plans/", plans_index, name="admin_plans_index"),
    path("admin/plans/add/", plan_create, name="admin_plan_create"),
    path("admin/plans/<int:plan_id>/edit/", plan_edit, name="admin_plan_edit"),
    path("admin/plans/delete/", plan_delete, name="admin_plan_delete"),
]
