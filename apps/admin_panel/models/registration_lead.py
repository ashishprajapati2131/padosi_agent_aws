from django.db import models


class RegistrationLead(models.Model):
    """One name+phone capture for the public popup and agent-registration gate."""

    STATUS_QUICK_REGISTERED = 'quick_registered'
    STATUS_FORM_STARTED = 'form_started'
    STATUS_FORM_COMPLETED = 'form_completed'
    STATUS_PAYMENT_COMPLETED = 'payment_completed'
    STATUS_CONVERTED = 'converted'
    STATUS_ABANDONED = 'abandoned'

    STATUS_CHOICES = [
        (STATUS_QUICK_REGISTERED, 'Quick Registered'),
        (STATUS_FORM_STARTED, 'Form Started'),
        (STATUS_FORM_COMPLETED, 'Form Completed'),
        (STATUS_PAYMENT_COMPLETED, 'Payment Completed'),
        (STATUS_CONVERTED, 'Converted'),
        (STATUS_ABANDONED, 'Abandoned'),
    ]

    PAYMENT_NONE = 'none'
    PAYMENT_PENDING = 'pending'
    PAYMENT_COMPLETED = 'completed'
    PAYMENT_FAILED = 'failed'
    PAYMENT_CHOICES = [
        (PAYMENT_NONE, 'Not started'),
        (PAYMENT_PENDING, 'Pending'),
        (PAYMENT_COMPLETED, 'Completed'),
        (PAYMENT_FAILED, 'Failed'),
    ]

    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, unique=True, db_index=True)
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_QUICK_REGISTERED,
        db_index=True,
    )
    form_filled = models.BooleanField(default=False)
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_CHOICES,
        default=PAYMENT_NONE,
        db_index=True,
    )
    source_url = models.CharField(max_length=500, blank=True, default='')
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=500, blank=True, default='')
    ref_code = models.CharField(max_length=50, blank=True, default='')
    draft_id = models.IntegerField(blank=True, null=True)
    agent_id = models.IntegerField(blank=True, null=True, db_index=True)
    converted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'registration_leads'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.phone})'

    @property
    def status_label(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)

    @property
    def payment_label(self):
        return dict(self.PAYMENT_CHOICES).get(self.payment_status, self.payment_status)

    @property
    def form_label(self):
        return 'Filled' if self.form_filled else 'Not filled'
