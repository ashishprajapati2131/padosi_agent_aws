"""Admin routes served by views/localization.py."""
from django.urls import path

from ..views import localization

urlpatterns = [
    path("admin/localization/", localization.localization_index, name="admin_localization"),
    path("admin/localization/settings/", localization.localization_settings_save, name="admin_localization_settings"),
    path("admin/localization/languages/", localization.localization_languages_save, name="admin_localization_languages"),
    path("admin/localization/states/", localization.localization_states_save, name="admin_localization_states"),
    path("admin/localization/texts/", localization.localization_texts_save, name="admin_localization_texts"),
    path("admin/localization/pages/", localization.localization_page_save, name="admin_localization_pages"),
]
