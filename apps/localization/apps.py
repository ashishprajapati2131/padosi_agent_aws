from django.apps import AppConfig


class LocalizationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.localization"
    verbose_name = "Localization (languages & regional detection)"
