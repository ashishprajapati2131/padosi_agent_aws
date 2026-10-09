import datetime
from django.db import models


class AppVersion(models.Model):
    """
    Mobile app version gate (Admin module #16 — Force-Update & App Version Control).

    One row per platform. The FastAPI mobile API reads this to tell the app
    whether an update is available (soft) or required (force).

    New, Django-owned table — safe to migrate (NOT a legacy Laravel table).
    """

    PLATFORM_CHOICES = [
        ('android', 'Android'),
        ('ios', 'iOS'),
    ]

    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, unique=True)
    latest_version = models.CharField(max_length=20, help_text="Newest version available on the store, e.g. 1.4.0")
    min_supported_version = models.CharField(max_length=20, help_text="Oldest version allowed to keep using the app, e.g. 1.2.0")
    force_update = models.BooleanField(default=False, help_text="If ON, apps below min_supported_version are hard-blocked.")
    update_message = models.CharField(max_length=255, blank=True, default='', help_text="Message shown on the update prompt.")
    store_url = models.CharField(max_length=500, blank=True, default='', help_text="Play Store / App Store link.")
    is_active = models.BooleanField(default=True, help_text="If OFF, the API reports no update for this platform.")
    created_at = models.DateTimeField(default=datetime.datetime.now)
    updated_at = models.DateTimeField(default=datetime.datetime.now)

    class Meta:
        db_table = 'app_versions'
        ordering = ['platform']

    def __str__(self):
        return f"{self.get_platform_display()} — latest {self.latest_version} / min {self.min_supported_version}"

    def save(self, *args, **kwargs):
        # USE_TZ=False project convention: naive local datetimes.
        self.updated_at = datetime.datetime.now()
        if not self.created_at:
            self.created_at = self.updated_at
        super().save(*args, **kwargs)
