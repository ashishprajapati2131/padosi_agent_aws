"""Admin routes served by views/free_trial.py."""
from django.urls import path

from ..views.free_trial import (
    free_trial_index,
    ft_update_trial_config,
    ft_update_upgrade_discount,
    ft_update_referral_config,
    ft_force_test_credit,
    ft_generate_promo,
    ft_update_promo,
    ft_toggle_promo,
    ft_delete_promo,
    ft_history,
    ft_analytics_data,
)

urlpatterns = [
    path("admin/free-trial/",                         free_trial_index,           name="admin_free_trial"),
    path("admin/free-trial/update-config/",           ft_update_trial_config,     name="admin_ft_update_config"),
    path("admin/free-trial/update-discount/",         ft_update_upgrade_discount, name="admin_ft_update_discount"),
    path("admin/free-trial/update-referral-config/",  ft_update_referral_config,  name="admin_ft_update_referral_config"),
    path("admin/free-trial/test-credit/",             ft_force_test_credit,       name="admin_ft_force_test_credit"),
    path("admin/free-trial/generate-promo/",          ft_generate_promo,          name="admin_ft_generate_promo"),
    path("admin/free-trial/promo/<int:promo_id>/update/", ft_update_promo,         name="admin_ft_update_promo"),
    path("admin/free-trial/toggle-promo/",            ft_toggle_promo,            name="admin_ft_toggle_promo"),
    path("admin/free-trial/promo/<int:promo_id>/delete/", ft_delete_promo,         name="admin_ft_delete_promo"),
    path("admin/free-trial/history/",                 ft_history,                 name="admin_ft_history"),
    path("admin/free-trial/analytics-data/",          ft_analytics_data,          name="admin_ft_analytics_data"),
]
