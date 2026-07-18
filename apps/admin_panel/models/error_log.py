from django.db import models
from django.utils import timezone

class ErrorLog(models.Model):
    LEVEL_CHOICES = [
        ('DEBUG', 'Debug'),
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('CRITICAL', 'Critical'),
    ]

    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    level = models.CharField(max_length=15, choices=LEVEL_CHOICES, default='ERROR', db_index=True)
    module = models.CharField(max_length=100, db_index=True)
    exception_type = models.CharField(max_length=255, db_index=True)
    message = models.TextField()
    stack_trace = models.TextField(null=True, blank=True)
    url = models.CharField(max_length=255, null=True, blank=True)
    method = models.CharField(max_length=10, null=True, blank=True)
    user_info = models.CharField(max_length=255, null=True, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'error_logs'
        verbose_name = 'Error Log'
        verbose_name_plural = 'Error Logs'

    def __str__(self):
        return f"[{self.level}] {self.exception_type} in {self.module} on {self.timestamp}"
