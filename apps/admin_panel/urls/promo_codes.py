"""Admin routes served by views/promo_codes.py."""
from django.urls import path

from ..views.promo_codes import (
    promo_code_list,
    store_promo_code,
    update_promo_code,
    toggle_promo_code_status,
)

urlpatterns = [
    path("admin/promo-codes/", promo_code_list, name="admin_promo_codes"),
    path("admin/promo-codes/store/", store_promo_code, name="admin_promo_code_store"),
    path("admin/promo-codes/<int:promo_id>/update/", update_promo_code, name="admin_promo_code_update"),
    path("admin/promo-codes/<int:promo_id>/toggle-status/", toggle_promo_code_status, name="admin_promo_code_toggle_status"),
]
