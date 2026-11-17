from django.conf import settings
from django.contrib import admin

from apps.localization.models import (
    ContentTranslation,
    LocalizationSettings,
    SiteLanguage,
    StateLanguage,
    UserLanguagePreference,
)
from apps.localization.services import translation_completion


@admin.register(SiteLanguage)
class SiteLanguageAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "native_name",
        "is_active",
        "sort_order",
        "translation_status",
    )
    list_editable = ("is_active", "sort_order")

    def get_readonly_fields(self, request, obj=None):
        return ("code",) if obj else ()

    def has_delete_permission(self, request, obj=None):
        return obj is None or obj.code != settings.LANGUAGE_CODE

    @admin.display(description="Translation completion")
    def translation_status(self, obj):
        done, total = translation_completion(obj.code)
        if not total:
            return "no catalog"
        return f"{round(100 * done / total)}% ({done}/{total})"


@admin.register(StateLanguage)
class StateLanguageAdmin(admin.ModelAdmin):
    list_display = ("state_name", "state_code", "aliases", "language")
    list_editable = ("language",)
    list_filter = ("language",)
    search_fields = ("state_name", "state_code", "aliases")


@admin.register(LocalizationSettings)
class LocalizationSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "auto_detect_enabled",
        "browser_language_enabled",
        "default_language",
    )

    def has_add_permission(self, request):
        return not LocalizationSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "default_language":
            kwargs["queryset"] = SiteLanguage.objects.filter(is_active=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(UserLanguagePreference)
class UserLanguagePreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "language", "updated_at")
    list_filter = ("language",)
    search_fields = ("user__email", "user__username")
    raw_id_fields = ("user",)


@admin.register(ContentTranslation)
class ContentTranslationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "language", "is_approved", "updated_at")
    list_editable = ("is_approved",)
    list_filter = ("language", "is_approved", "content_type")
    search_fields = ("object_id", "field", "text")
