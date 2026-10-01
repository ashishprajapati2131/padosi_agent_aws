import random
import string
from datetime import datetime, timedelta

from django.db import models

from apps.agents.models import Agent


def _now():
    return datetime.now()


class EventReferralCampaign(models.Model):
    """Singleton-style campaign settings (use get_current())."""

    is_enabled = models.BooleanField(default=True)
    window_hours = models.PositiveIntegerField(default=48)
    required_paid_referrals = models.PositiveIntegerField(default=5)
    reward_plan_slug = models.CharField(max_length=50, default='basic')
    page_title = models.CharField(max_length=255, default='Paldi Registration')
    page_instructions = models.TextField(
        blank=True,
        default=(
            'Welcome to Paldi! Register below, preview your agent card and profile website, '
            'then share your link. Refer 5 agents who complete payment within 48 hours to unlock your Basic plan.'
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'event_referral_campaigns'

    def __str__(self):
        return f'Event Referral Campaign (enabled={self.is_enabled})'

    def save(self, *args, **kwargs):
        from django.core.cache import cache
        try:
            cache.delete('current_event_referral_campaign')
        except Exception:
            pass
        super().save(*args, **kwargs)

    @classmethod
    def get_current(cls):
        from django.core.cache import cache
        try:
            cached = cache.get('current_event_referral_campaign')
            if cached is not None:
                return cached
        except Exception:
            pass

        campaign = cls.objects.order_by('-id').first()
        if not campaign:
            campaign = cls.objects.create()

        try:
            cache.set('current_event_referral_campaign', campaign, timeout=60)
        except Exception:
            pass
        return campaign


class EventReferralParticipant(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_WON = 'won'
    STATUS_BLOCKED = 'blocked'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_WON, 'Won'),
        (STATUS_BLOCKED, 'Blocked'),
    ]

    campaign = models.ForeignKey(
        EventReferralCampaign,
        on_delete=models.CASCADE,
        related_name='participants',
    )
    agent = models.OneToOneField(
        Agent,
        on_delete=models.CASCADE,
        related_name='event_referral_participant',
        db_constraint=False,
    )
    referral_code = models.CharField(max_length=50, unique=True, db_index=True)
    registered_at = models.DateTimeField()
    deadline_at = models.DateTimeField(db_index=True)
    window_hours = models.PositiveIntegerField()
    required_paid_referrals = models.PositiveIntegerField()
    reward_plan_slug = models.CharField(max_length=50, default='basic')
    paid_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    won_at = models.DateTimeField(null=True, blank=True)
    blocked_at = models.DateTimeField(null=True, blank=True)
    blocked_reason = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'event_referral_participants'
        ordering = ['-registered_at']

    def __str__(self):
        return f'{self.referral_code} ({self.status}, {self.paid_count}/{self.required_paid_referrals})'

    @staticmethod
    def generate_referral_code():
        while True:
            suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            code = f'EV-{suffix}'
            if not EventReferralParticipant.objects.filter(referral_code=code).exists():
                return code

    @classmethod
    def create_for_agent(cls, agent, campaign=None):
        existing = cls.objects.filter(agent=agent).first()
        if existing:
            return existing
        if campaign is None:
            campaign = EventReferralCampaign.get_current()
        now = _now()
        for _ in range(5):
            code = cls.generate_referral_code()
            try:
                return cls.objects.create(
                    campaign=campaign,
                    agent=agent,
                    referral_code=code,
                    registered_at=now,
                    deadline_at=now + timedelta(hours=int(campaign.window_hours)),
                    window_hours=campaign.window_hours,
                    required_paid_referrals=campaign.required_paid_referrals,
                    reward_plan_slug=campaign.reward_plan_slug or 'basic',
                    paid_count=0,
                    status=cls.STATUS_ACTIVE,
                )
            except Exception:
                existing = cls.objects.filter(agent=agent).first()
                if existing:
                    return existing
        return cls.objects.filter(agent=agent).first()


class EventReferral(models.Model):
    STATE_REGISTERED = 'registered'
    STATE_PAID = 'paid'
    STATE_REFUNDED = 'refunded'
    STATE_REJECTED = 'rejected'
    STATE_CHOICES = [
        (STATE_REGISTERED, 'Registered'),
        (STATE_PAID, 'Paid'),
        (STATE_REFUNDED, 'Refunded'),
        (STATE_REJECTED, 'Rejected'),
    ]

    participant = models.ForeignKey(
        EventReferralParticipant,
        on_delete=models.CASCADE,
        related_name='referrals',
    )
    referred_agent = models.OneToOneField(
        Agent,
        on_delete=models.CASCADE,
        related_name='event_referral_attribution',
        db_constraint=False,
    )
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_REGISTERED)
    counts = models.BooleanField(default=False)
    registered_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    snapshot_name = models.CharField(max_length=255, blank=True, default='')
    snapshot_email = models.CharField(max_length=255, blank=True, default='')
    snapshot_mobile = models.CharField(max_length=50, blank=True, default='')
    snapshot_city = models.CharField(max_length=255, blank=True, default='')
    snapshot_plan = models.CharField(max_length=50, blank=True, default='')
    snapshot_payment_status = models.CharField(max_length=50, blank=True, default='')
    reject_reason = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'event_referral_referrals'
        ordering = ['-registered_at']
        indexes = [
            models.Index(fields=['participant', 'state'], name='ev_ref_part_state_idx'),
            models.Index(fields=['participant', 'counts'], name='ev_ref_part_counts_idx'),
        ]

    def __str__(self):
        return f'{self.snapshot_name or self.referred_agent_id} → {self.participant.referral_code}'
