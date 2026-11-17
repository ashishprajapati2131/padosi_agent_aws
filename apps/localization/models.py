from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


class SiteLanguage(models.Model):
    """A language the site can be served in. Codes are limited to settings.LANGUAGES
    (each needs a locale/<code>/ catalog); admins control availability and order."""

    code = models.CharField(max_length=10, primary_key=True, choices=settings.LANGUAGES)
    native_name = models.CharField(
        max_length=50, help_text="Shown in the language switcher, e.g. ગુજરાતી"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Available on the site: switcher, /<code>/ URLs, sitemap and auto-detection.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "localization_languages"
        ordering = ("sort_order", "code")

    def __str__(self):
        return f"{self.native_name} ({self.code})"

    def save(self, *args, **kwargs):
        if self.code == settings.LANGUAGE_CODE:
            self.is_active = True  # the source language always stays available
        super().save(*args, **kwargs)


class StateLanguage(models.Model):
    """Indian state / union territory -> language used for GeoIP auto-detection."""

    state_code = models.CharField(
        max_length=8,
        unique=True,
        help_text="ISO 3166-2:IN subdivision code without 'IN-', e.g. GJ",
    )
    state_name = models.CharField(max_length=100)
    aliases = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated alternate codes/names GeoIP providers may return, e.g. TS,TG",
    )
    language = models.ForeignKey(
        SiteLanguage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Empty = no automatic switch for visitors from this state.",
    )

    class Meta:
        db_table = "localization_state_languages"
        ordering = ("state_name",)

    def __str__(self):
        return f"{self.state_name} -> {self.language_id or '-'}"


class LocalizationSettings(models.Model):
    """Singleton (pk=1) with site-wide detection switches."""

    enabled = models.BooleanField(
        default=True,
        help_text="Master switch. OFF = English only: no switcher, no /<lang>/ URLs, no auto-detection.",
    )
    auto_detect_enabled = models.BooleanField(
        default=True, help_text="Use the visitor's GeoIP state to pick a language."
    )
    browser_language_enabled = models.BooleanField(
        default=True,
        help_text="Use the browser's Accept-Language when no state language applies.",
    )
    default_language = models.ForeignKey(
        SiteLanguage,
        on_delete=models.PROTECT,
        default=settings.LANGUAGE_CODE,
        help_text="Fallback when nothing else decides. Unprefixed URLs always serve the source language.",
    )

    class Meta:
        db_table = "localization_settings"
        verbose_name = verbose_name_plural = "Localization settings"

    def __str__(self):
        return "Localization settings"

    def clean(self):
        if (
            self.default_language_id
            and not SiteLanguage.objects.filter(
                pk=self.default_language_id, is_active=True
            ).exists()
        ):
            raise ValidationError(
                {"default_language": "The default language must be active."}
            )

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)


class UserLanguagePreference(models.Model):
    """Language a signed-in auth_user picked in the switcher (follows them across devices)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="language_preference",
    )
    language = models.CharField(max_length=10, choices=settings.LANGUAGES)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "localization_user_preferences"

    def __str__(self):
        return f"{self.user_id}: {self.language}"


class UITranslation(models.Model):
    """Admin edit of one website text (a msgid from locale/*.po) in one language.
    Overrides the .po file value at runtime, so no deploy is needed to fix wording."""

    language = models.CharField(max_length=10, choices=settings.LANGUAGES)
    msgid = models.CharField(max_length=500)  # CharField: MySQL cannot index TEXT in a unique key
    text = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "localization_ui_translations"
        constraints = [
            models.UniqueConstraint(fields=["language", "msgid"], name="uniq_ui_translation"),
        ]

    def __str__(self):
        return f"[{self.language}] {self.msgid[:40]}"


class ContentTranslation(models.Model):
    """Admin-entered translation of one field of a database row (CMS pages, settings, ...).

    Only approved rows are shown, so nothing (and never user-generated content)
    is translated without someone explicitly writing and approving it.
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=64)
    field = models.CharField(max_length=64, help_text="Model field name, e.g. title")
    language = models.CharField(max_length=10, choices=settings.LANGUAGES)
    text = models.TextField()
    is_approved = models.BooleanField(
        default=False, help_text="Only approved translations are shown."
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "localization_content_translations"
        unique_together = ("content_type", "object_id", "field", "language")

    def __str__(self):
        return (
            f"{self.content_type.model}#{self.object_id}.{self.field} [{self.language}]"
        )


@receiver([post_save, post_delete], sender=SiteLanguage)
@receiver([post_save, post_delete], sender=StateLanguage)
@receiver([post_save, post_delete], sender=LocalizationSettings)
@receiver([post_save, post_delete], sender=UITranslation)
def _clear_config_cache(**kwargs):
    from apps.localization.services import clear_config_cache

    clear_config_cache()


@receiver([post_save, post_delete], sender=ContentTranslation)
def _clear_content_translation_cache(instance, **kwargs):
    from apps.localization.services import content_translation_cache_key
    from django.core.cache import cache

    cache.delete(
        content_translation_cache_key(
            instance.content_type_id,
            instance.object_id,
            instance.field,
            instance.language,
        )
    )
