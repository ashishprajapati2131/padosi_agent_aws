"""Admin routes served by views/blacklisted.py."""
from django.urls import path

from apps.admin_panel.views.blacklisted import (
    blacklisted_agents_view,
    ajax_blacklist_approve,
    ajax_blacklist_confirm,
    ajax_blacklist_remove,
)

urlpatterns = [
    path('admin/blacklisted-agents/', blacklisted_agents_view, name='admin_blacklisted_agents'),
    path('admin/ajax/blacklist/approve/', ajax_blacklist_approve, name='ajax_blacklist_approve'),
    path('admin/ajax/blacklist/confirm/', ajax_blacklist_confirm, name='ajax_blacklist_confirm'),
    path('admin/ajax/blacklist/remove/', ajax_blacklist_remove, name='ajax_blacklist_remove'),
]
