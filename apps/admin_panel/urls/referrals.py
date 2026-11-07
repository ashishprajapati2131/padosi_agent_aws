"""Admin routes served by views/referrals.py."""
from django.urls import path

from ..views.referrals import (
    admin_referrals_index,
    admin_referrals_toggle_code,
    admin_referrals_mark_claimed,
    admin_referrals_generate_missing,
    admin_referrals_update_tiers,
)

urlpatterns = [
    path("admin/referrals/",                            admin_referrals_index,           name="admin_referrals_index"),
    path("admin/referrals/toggle-code/",                admin_referrals_toggle_code,     name="admin_referrals_toggle_code"),
    path("admin/referrals/<int:code_id>/mark-claimed/", admin_referrals_mark_claimed,    name="admin_referrals_mark_claimed"),
    path("admin/referrals/generate-missing-codes/",    admin_referrals_generate_missing, name="admin_referrals_generate_missing"),
    path("admin/referrals/update-tiers/",              admin_referrals_update_tiers,    name="admin_referrals_update_tiers"),
]
