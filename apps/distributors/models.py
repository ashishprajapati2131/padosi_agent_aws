import random
import string
from django.db import models
from django.utils import timezone


class SubDistributor(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('inactive', 'Inactive'),
    )

    distributor_id = models.IntegerField(db_index=True, help_text="ID of parent distributor in users table")
    fullname = models.CharField(max_length=191)
    email = models.CharField(max_length=191, unique=True)
    mobile = models.CharField(max_length=20, db_index=True)
    password = models.CharField(max_length=255)
    code = models.CharField(max_length=64, unique=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    clicks = models.IntegerField(default=0)
    notes = models.TextField(blank=True, default='')
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sub_distributors'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.fullname} ({self.code})"

    @classmethod
    def generate_unique_code(cls, distributor_id, name=""):
        clean_name = ''.join(c for c in (name or '').upper() if c.isalnum())[:3]
        prefix = f"SUB{distributor_id}{clean_name}" if clean_name else f"SUB{distributor_id}"
        while True:
            suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            candidate = f"{prefix}{suffix}"
            if not cls.objects.filter(code=candidate).exists():
                return candidate

    def get_parent_distributor(self):
        from apps.admin_panel.models import User as LaravelUser
        return LaravelUser.objects.filter(id=self.distributor_id).first()

    def get_total_agents_count(self):
        from apps.agents.models import Agent
        return Agent.objects.filter(sub_distributor_id=self.id).count()

    def get_active_agents_count(self):
        from apps.agents.models import Agent
        return Agent.objects.filter(sub_distributor_id=self.id, status='active').count()

    def get_draft_agents_count(self):
        from apps.agents.models import AgentDraft, Agent
        agent_emails = set(Agent.objects.filter(sub_distributor_id=self.id).values_list('email', flat=True))
        return AgentDraft.objects.filter(sub_distributor_id=self.id, registration_step__gte=1).exclude(email__in=agent_emails).count()
