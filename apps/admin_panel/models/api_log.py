from django.db import models
from django.utils import timezone

class ApiLog(models.Model):
    service = models.CharField(max_length=50, default='fastapi', db_index=True)
    request_url = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    payload = models.JSONField(null=True, blank=True)
    response = models.JSONField(null=True, blank=True)
    response_code = models.IntegerField(null=True, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = 'api_logs'
        verbose_name = 'API Log'
        verbose_name_plural = 'API Logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.response_code}] {self.method} {self.request_url} ({self.service})"
