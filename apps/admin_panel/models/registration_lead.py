from django.db import models


class RegistrationLead(models.Model):
    """Name and phone captured on /quick-registration/ before full registration."""

    STATUS_CHOICES = [
        ('Started', 'Started'),
        ('Completed', 'Completed'),
        ('Abandoned', 'Abandoned'),
    ]

    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Started')
    source_url = models.CharField(max_length=500, blank=True, default='')
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=500, blank=True, default='')
    ref_code = models.CharField(max_length=50, blank=True, default='')
    draft_id = models.IntegerField(blank=True, null=True)
    agent_id = models.IntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'registration_leads'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.phone})'
