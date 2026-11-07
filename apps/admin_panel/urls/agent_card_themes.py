"""Admin routes served by views/agent_card_themes.py."""
from django.urls import path

from ..views import agent_card_themes as card_themes

urlpatterns = [
    path("admin/agent-card-themes/", card_themes.agent_card_themes_index, name="admin_agent_card_themes"),
    path("admin/agent-card-themes/save/", card_themes.agent_card_theme_save, name="admin_agent_card_theme_save"),
    path("admin/agent-card-themes/activate/", card_themes.agent_card_theme_activate, name="admin_agent_card_theme_activate"),
    path("admin/agent-card-themes/delete/", card_themes.agent_card_theme_delete, name="admin_agent_card_theme_delete"),
    path("admin/agent-card-themes/preset/", card_themes.agent_card_theme_preset, name="admin_agent_card_theme_preset"),
    path("admin/agent-card-themes/import/", card_themes.agent_card_theme_import, name="admin_agent_card_theme_import"),
    path("admin/agent-card-themes/<slug:theme_id>/export/", card_themes.agent_card_theme_export, name="admin_agent_card_theme_export"),
    path("admin/agent-card-themes/flag/", card_themes.agent_card_theme_flag, name="admin_agent_card_theme_flag"),
    path("admin/agent-card-themes/preview/", card_themes.agent_card_theme_preview, name="admin_agent_card_theme_preview"),
]
