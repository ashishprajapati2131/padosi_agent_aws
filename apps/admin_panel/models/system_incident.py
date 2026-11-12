from datetime import timedelta

from django.db import models


class SystemIncident(models.Model):
    """One row per ongoing failure seen by the system monitor, however many checks saw it.

    Written by apps/admin_panel/services/system_monitor.py. While the database
    itself is down the incident lives in the cache and the row is written on
    the first check that can reach the database again.
    """

    incident_id = models.CharField(max_length=32, unique=True)
    service = models.CharField(max_length=20)  # "database" or "server"
    title = models.CharField(max_length=150)
    reasons = models.JSONField(default=list)
    metrics = models.JSONField(default=dict)  # snapshot at first detection
    first_detected_at = models.DateTimeField(db_index=True)
    last_detected_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    failed_checks = models.PositiveIntegerField(default=1)
    alert_sent = models.BooleanField(default=False)

    class Meta:
        db_table = "system_incidents"
        ordering = ["-first_detected_at"]

    def __str__(self):
        return f"{self.incident_id} {self.title} ({self.status})"

    @property
    def status(self):
        return "RESOLVED" if self.resolved_at else "DETECTED"

    @property
    def duration(self):
        """Time from first detection to recovery (or to the last failed check while open)."""
        end = self.resolved_at or self.last_detected_at
        return timedelta(seconds=int((end - self.first_detected_at).total_seconds()))
