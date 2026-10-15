"""
Bulk CSV / Excel Product Import Models.
"""
from django.db import models
from datetime import datetime
from .profile import WholesalerProfile

class BulkImportJob(models.Model):
    """Tracks batch product CSV upload operations."""
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending Validation'),
        ('PROCESSING', 'Processing Rows'),
        ('COMPLETED', 'Completed Successfully'),
        ('PARTIAL', 'Completed with Errors'),
        ('FAILED', 'Failed / Invalid File'),
    ]
    
    wholesaler = models.ForeignKey(
        WholesalerProfile,
        on_delete=models.CASCADE,
        related_name='import_jobs'
    )
    file = models.FileField(upload_to='wholesale/imports/%Y/%m/')
    original_filename = models.CharField(max_length=255)
    
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='PENDING')
    total_rows = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    
    summary_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=datetime.now)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'ws_bulk_import_jobs'
        verbose_name = 'Bulk Import Job'
        verbose_name_plural = 'Bulk Import Jobs'
        ordering = ['-created_at']

    def __str__(self):
        return f"Import #{self.id} - {self.original_filename} ({self.get_status_display()})"


class BulkImportError(models.Model):
    """Row-level validation errors from bulk CSV uploads."""
    
    job = models.ForeignKey(
        BulkImportJob,
        on_delete=models.CASCADE,
        related_name='errors'
    )
    row_number = models.PositiveIntegerField()
    sku = models.CharField(max_length=100, blank=True, null=True)
    error_field = models.CharField(max_length=100, blank=True, null=True)
    error_message = models.TextField()

    class Meta:
        db_table = 'ws_bulk_import_errors'
        verbose_name = 'Bulk Import Error'
        verbose_name_plural = 'Bulk Import Errors'
        ordering = ['row_number']

    def __str__(self):
        return f"Row {self.row_number} [{self.sku}]: {self.error_message}"
