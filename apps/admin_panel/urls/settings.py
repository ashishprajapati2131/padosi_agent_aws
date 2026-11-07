"""Admin routes served by views/settings.py."""
from django.urls import path

from ..views import settings

urlpatterns = [
    path("admin/settings/general/",         settings.general,             name="admin_settings_general"),
    path("admin/settings/seo/",             settings.seo,                 name="admin_settings_seo"),
    path("admin/settings/seo/link-og/save/", settings.link_og_save,        name="admin_link_og_save"),
    path("admin/settings/seo/link-og/<int:rule_id>/delete/", settings.link_og_delete, name="admin_link_og_delete"),
    path("admin/settings/seo/link-og/<int:rule_id>/toggle/", settings.link_og_toggle, name="admin_link_og_toggle"),
    path("admin/settings/banner-popup/",    settings.banner_popup_studio, name="admin_settings_banner_popup"),
    path("admin/settings/banner-popup/save-banner/", settings.save_banner_settings, name="admin_save_banner_settings"),
    path("admin/settings/banner-popup/save-popup/", settings.save_popup_settings, name="admin_save_popup_settings"),
    path("admin/settings/banner-popup/toggle/<str:target>/", settings.toggle_banner_popup, name="admin_toggle_banner_popup"),
    path("admin/settings/security/",        settings.security,            name="admin_settings_security"),
    path("admin/settings/templates/",       settings.templates,           name="admin_settings_templates"),
    path("admin/settings/templates/update/",settings.update_templates,    name="admin_settings_templates_update"),
    path("admin/settings/update/",          settings.update_settings,     name="admin_settings_update"),
    path("admin/settings/wa-bot/toggle/",   settings.toggle_wa_bot_service, name="admin_toggle_wa_bot_service"),
    path("admin/settings/homepage/",        settings.homepage,            name="admin_settings_homepage"),
    path("admin/settings/homepage/update/", settings.update_homepage,     name="admin_settings_homepage_update"),
    path("admin/settings/hero-section/",    settings.hero_section,        name="admin_settings_hero_section"),
    path("admin/settings/hero-section/update/", settings.update_hero_section, name="admin_settings_hero_section_update"),
]
