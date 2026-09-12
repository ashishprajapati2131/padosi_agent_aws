from django.urls import path
from apps.referral_championship.views import admin_views

urlpatterns = [
    path('', admin_views.admin_championship_dashboard, name='admin_championship_dashboard'),
    path('settings/update/', admin_views.admin_update_campaign_settings, name='admin_championship_update_settings'),
    path('rewards/manage/', admin_views.admin_manage_reward_slab, name='admin_championship_manage_reward'),
    path('leaderboard/', admin_views.admin_leaderboard_view, name='admin_championship_leaderboard'),
    path('leaderboard/freeze/', admin_views.admin_freeze_leaderboard, name='admin_championship_freeze_leaderboard'),
    path('referral-tree/', admin_views.admin_referral_tree_view, name='admin_championship_referral_tree'),
    path('fraud/', admin_views.admin_fraud_control_view, name='admin_championship_fraud'),
    path('fraud/<int:flag_id>/resolve/', admin_views.admin_resolve_fraud_flag, name='admin_championship_resolve_fraud'),
]
