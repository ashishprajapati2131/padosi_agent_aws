"""Admin routes served by views/payment_reconcile.py."""
from django.urls import path

from ..views.payment_reconcile import (
    payment_reconcile_dashboard,
    reconcile_inspect_payment,
    reconcile_execute_payment,
)

urlpatterns = [
    path("admin/payments/reconcile/", payment_reconcile_dashboard, name="admin_payment_reconcile"),
    path("admin/payments/reconcile/inspect/", reconcile_inspect_payment, name="admin_payment_reconcile_inspect"),
    path("admin/payments/reconcile/execute/", reconcile_execute_payment, name="admin_payment_reconcile_execute"),
]
