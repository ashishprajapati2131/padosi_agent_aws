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
    # Columns added by migrations 0003 and 0005 (fields were missing here).
    closed_message = models.TextField(
        blank=True,
        default=(
            'This registration link is deactivated for now. '
            'Please wait until it opens again.'
        ),
    )
    registration_link_open_count = models.PositiveBigIntegerField(default=0)
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
    # Columns added by migration 0005 (fields were missing here).
    page_active_seconds = models.PositiveIntegerField(default=0)
    blocked_by_admin = models.BooleanField(default=False, db_index=True)
    # Admin "Grant plan" on the event-referral page. Empty slug means no
    # manual grant. A null expiry means the grant does not expire.
    grant_plan_slug = models.CharField(max_length=50, blank=True, default='')
    grant_expires_at = models.DateTimeField(null=True, blank=True)
    grant_previous_plan = models.CharField(max_length=50, blank=True, default='')
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


class TrialAgentActivityLog(models.Model):
    """
    Audit and activity log for all Free Trial agents (Paldi festive trial, event challenge, standard trials).
    Tracks logins, profile edits, public profile/card views, upgrade checkout attempts, and completed plan upgrades.
    """
    ACTIVITY_LOGIN = 'login'
    ACTIVITY_DASHBOARD = 'dashboard_view'
    ACTIVITY_PROFILE_EDIT = 'profile_edit'
    ACTIVITY_PROFILE_VIEW = 'profile_view'
    ACTIVITY_CARD_VIEW = 'card_view'
    ACTIVITY_CARD_DOWNLOAD = 'card_download'
    ACTIVITY_QR_DOWNLOAD = 'qr_download'
    ACTIVITY_VCF_DOWNLOAD = 'vcf_download'
    ACTIVITY_UPGRADE_MODAL_OPEN = 'upgrade_modal_open'
    ACTIVITY_UPGRADE_INITIATED = 'upgrade_initiated'
    ACTIVITY_UPGRADE_SUCCESS = 'upgrade_success'
    ACTIVITY_UPGRADE_FAILED = 'upgrade_failed'
    ACTIVITY_LEAD_RECEIVED = 'lead_received'
    ACTIVITY_REVIEW_SUBMITTED = 'review_submitted'

    ACTIVITY_CHOICES = [
        (ACTIVITY_LOGIN, 'Agent Logged In'),
        (ACTIVITY_DASHBOARD, 'Dashboard Visited'),
        (ACTIVITY_PROFILE_EDIT, 'Profile Edited'),
        (ACTIVITY_PROFILE_VIEW, 'Profile Viewed'),
        (ACTIVITY_CARD_VIEW, 'Visiting Card Viewed'),
        (ACTIVITY_CARD_DOWNLOAD, 'Visiting Card Downloaded'),
        (ACTIVITY_QR_DOWNLOAD, 'QR Code Downloaded'),
        (ACTIVITY_VCF_DOWNLOAD, 'Contact (VCF) Saved'),
        (ACTIVITY_UPGRADE_MODAL_OPEN, 'Upgrade Modal Opened'),
        (ACTIVITY_UPGRADE_INITIATED, 'Upgrade Checkout Initiated'),
        (ACTIVITY_UPGRADE_SUCCESS, 'Plan Upgraded (Payment Succeeded)'),
        (ACTIVITY_UPGRADE_FAILED, 'Upgrade Payment Failed'),
        (ACTIVITY_LEAD_RECEIVED, 'Lead Received from Card'),
        (ACTIVITY_REVIEW_SUBMITTED, 'Review Received'),
    ]

    agent = models.ForeignKey(
        Agent,
        on_delete=models.CASCADE,
        related_name='trial_activity_logs',
        db_constraint=False,
    )
    participant = models.ForeignKey(
        EventReferralParticipant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
        db_constraint=False,
    )
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_CHOICES, db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.CharField(max_length=45, blank=True, default='')
    user_agent = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'trial_agent_activity_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['agent', '-created_at'], name='trial_act_agent_idx'),
            models.Index(fields=['activity_type', '-created_at'], name='trial_act_type_idx'),
        ]

    def __str__(self):
        return f'{self.agent_id} - {self.activity_type} ({self.created_at})'

    @classmethod
    def is_trial_agent(cls, agent):
        if not agent:
            return False
        try:
            if hasattr(agent, 'isOnFreeTrial') and agent.isOnFreeTrial():
                return True
            if hasattr(agent, 'isTrialExpired') and agent.isTrialExpired():
                return True
            if getattr(agent, 'status', None) in ('event_challenge', 'trial'):
                return True
            if getattr(agent, 'plan_type', None) == 'free_trial':
                return True
            if hasattr(agent, 'event_referral_participant'):
                return True
            if EventReferralParticipant.objects.filter(agent_id=agent.id).exists():
                return True
        except Exception:
            pass
        return False

    @classmethod
    def log(cls, agent, activity_type, title, description="", details=None, request=None, force=False):
        import logging
        _logger = logging.getLogger(__name__)
        try:
            if not agent:
                return None
            if not force and not cls.is_trial_agent(agent):
                return None

            participant = getattr(agent, 'event_referral_participant', None)
            if participant is None:
                try:
                    participant = EventReferralParticipant.objects.filter(agent_id=agent.id).first()
                except Exception:
                    participant = None

            ip = ""
            ua = ""
            if request is not None:
                try:
                    from apps.admin_panel.middleware import ThreatMonitorMiddleware
                    ip = ThreatMonitorMiddleware.get_client_ip(request) or ""
                except Exception:
                    ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR', '')
                ua = (request.META.get('HTTP_USER_AGENT', '') or '')[:500]

            return cls.objects.create(
                agent=agent,
                participant=participant,
                activity_type=activity_type,
                title=(title or "")[:255],
                description=description or "",
                details=details or {},
                ip_address=(ip or "")[:45],
                user_agent=(ua or "")[:500],
            )
        except Exception as e:
            _logger.warning("Failed to record trial activity log: %s", e)
            return None

