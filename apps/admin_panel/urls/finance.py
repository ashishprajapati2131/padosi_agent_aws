"""Admin routes served by views/finance.py."""
from django.urls import path

from ..views import finance

urlpatterns = [
    path("admin/finance/", finance.index, name="admin_finance_index"),
    path("admin/finance/mark-payment/", finance.mark_payment, name="admin_finance_mark_payment"),
]
