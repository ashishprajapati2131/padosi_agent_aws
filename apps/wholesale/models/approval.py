"""
Product Approval Workflow and Audit History Models.
"""
from django.db import models
from datetime import datetime
from .product import WholesaleProduct

class ProductApprovalLog(models.Model):
    """Immutable audit trail of product approval actions, transitions, and notes."""
    
    ACTION_CHOICES = [
        ('SUBMITTED', 'Submitted for Approval'),
        ('ASSIGNED_REVIEW', 'Assigned for Review'),
        ('CHANGES_REQUESTED', 'Changes / Revisions Requested'),
        ('RESUBMITTED', 'Resubmitted with Changes'),
        ('APPROVED', 'Approved by Admin'),
        ('PUBLISHED', 'Published to Marketplace'),
        ('REJECTED', 'Rejected'),
        ('PAUSED', 'Paused by Seller/Admin'),
        ('ARCHIVED', 'Archived'),
    ]
    
    product = models.ForeignKey(
        WholesaleProduct,
        on_delete=models.CASCADE,
        related_name='approval_logs'
    )
    actor_username = models.CharField(max_length=150, help_text="Username of admin or seller performing the action")
    actor_role = models.CharField(max_length=50, default='ADMIN', help_text="ADMIN, SELLER, or SYSTEM")
    
    action = models.CharField(max_length=40, choices=ACTION_CHOICES)
    from_status = models.CharField(max_length=30)
    to_status = models.CharField(max_length=30)
    
    notes_to_seller = models.TextField(blank=True, null=True, help_text="Feedback or instructions sent to the seller")
    internal_notes = models.TextField(blank=True, null=True, help_text="Private admin notes not seen by seller")
    snapshot_data = models.JSONField(blank=True, null=True, help_text="Snapshot of product attributes at this decision")
    
    created_at = models.DateTimeField(default=datetime.now)

    class Meta:
        db_table = 'ws_product_approval_logs'
        verbose_name = 'Product Approval Log'
        verbose_name_plural = 'Product Approval Logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product.sku}: {self.get_action_display()} by {self.actor_username} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
