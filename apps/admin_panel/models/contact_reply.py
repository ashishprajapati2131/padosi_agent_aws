import datetime
from django.db import models

from apps.admin_panel.models.contact_submission import ContactSubmission


class ContactReply(models.Model):
    """
    A reply or internal note on a support ticket (module #8).

    - is_internal_note=False  → a reply sent to the customer (optionally emailed)
    - is_internal_note=True   → a private note visible only to admins

    New, Django-owned table. Existing contacts flow is unaffected.
    """
    submission = models.ForeignKey(
        ContactSubmission,
        on_delete=models.CASCADE,
        related_name='replies',
        db_column='submission_id',
    )
    admin_id        = models.IntegerField(null=True, blank=True)
    admin_name      = models.CharField(max_length=255, blank=True, default='')
    message         = models.TextField()
    is_internal_note = models.BooleanField(default=False)
    emailed         = models.BooleanField(default=False)
    created_at      = models.DateTimeField(default=datetime.datetime.now)

    class Meta:
        db_table = 'contact_replies'
        ordering = ['created_at']

    def __str__(self):
        kind = 'Note' if self.is_internal_note else 'Reply'
        return f"{kind} on ticket #{self.submission_id} by {self.admin_name or self.admin_id}"
