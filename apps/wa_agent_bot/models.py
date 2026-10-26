"""
WhatsApp Agent Bot — Database Models

Tracks conversation state for each WhatsApp phone number through the
registration flow and post-login command handling.
"""

from django.db import models
from django.utils import timezone


class WaBotSession(models.Model):
    """
    Tracks the state of each WhatsApp conversation for agent registration
    and post-login command handling. One session per unique phone number.
    """

    # ── State constants ─────────────────────────────────────────────────
    STATE_WELCOME = 'welcome'
    STATE_ASK_FULLNAME = 'ask_fullname'
    STATE_ASK_EMAIL = 'ask_email'
    STATE_ASK_MOBILE = 'ask_mobile'
    STATE_ASK_STATE = 'ask_state'
    STATE_ASK_PINCODE = 'ask_pincode'
    STATE_ASK_EXPERIENCE = 'ask_experience'
    STATE_ASK_SEGMENTS = 'ask_segments'
    STATE_CONFIRM_DETAILS = 'confirm_details'
    STATE_ASK_PLAN = 'ask_plan'
    STATE_AWAITING_PAYMENT = 'awaiting_payment'
    STATE_CREATING_ACCOUNT = 'creating_account'
    STATE_REGISTRATION_DONE = 'registration_done'
    STATE_LOGGED_IN = 'logged_in'

    STATE_CHOICES = [
        (STATE_WELCOME, 'Welcome'),
        (STATE_ASK_FULLNAME, 'Ask Full Name'),
        (STATE_ASK_EMAIL, 'Ask Email'),
        (STATE_ASK_MOBILE, 'Ask Mobile'),
        (STATE_ASK_STATE, 'Ask State'),
        (STATE_ASK_PINCODE, 'Ask Pincode'),
        (STATE_ASK_EXPERIENCE, 'Ask Experience'),
        (STATE_ASK_SEGMENTS, 'Ask Segments'),
        (STATE_CONFIRM_DETAILS, 'Confirm Details'),
        (STATE_ASK_PLAN, 'Ask Plan Selection'),
        (STATE_AWAITING_PAYMENT, 'Awaiting Payment'),
        (STATE_CREATING_ACCOUNT, 'Creating Account'),
        (STATE_REGISTRATION_DONE, 'Registration Done'),
        (STATE_LOGGED_IN, 'Logged In'),
    ]

    # ── Fields ──────────────────────────────────────────────────────────
    phone_number = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text='WhatsApp number in international format, e.g. 919876543210',
    )
    state = models.CharField(
        max_length=50,
        choices=STATE_CHOICES,
        default=STATE_WELCOME,
        db_index=True,
    )
    registration_data = models.JSONField(
        default=dict,
        blank=True,
        help_text='Accumulated registration form data collected during the conversation',
    )
    agent = models.ForeignKey(
        'agents.Agent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='wa_bot_sessions',
        help_text='Linked agent record after successful registration',
        db_constraint=False,
    )
    is_registered = models.BooleanField(
        default=False,
        help_text='True once the agent account has been created',
    )
    is_logged_in = models.BooleanField(
        default=False,
        help_text='True once the agent has received credentials and is in post-login mode',
    )
    generated_password = models.CharField(
        max_length=128,
        blank=True,
        default='',
        help_text='Temporary generated password (sent once, should be changed on first login)',
    )
    session_context = models.JSONField(
        default=dict,
        blank=True,
        help_text='Temporary context data for multi-step operations',
    )
    message_count = models.PositiveIntegerField(
        default=0,
        help_text='Total messages received in this session',
    )
    last_message_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of the last incoming message',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wa_bot_sessions'
        ordering = ['-updated_at']
        verbose_name = 'WhatsApp Bot Session'
        verbose_name_plural = 'WhatsApp Bot Sessions'

    def __str__(self):
        return f"WaBotSession({self.phone_number}, state={self.state})"

    def update_last_activity(self):
        """Bump the message count and last-activity timestamp."""
        self.message_count += 1
        self.last_message_at = timezone.now()


class WaBotMessageLog(models.Model):
    """
    Audit log of all messages sent and received through the bot.
    Useful for debugging and analytics.
    """

    DIRECTION_IN = 'in'
    DIRECTION_OUT = 'out'
    DIRECTION_CHOICES = [
        (DIRECTION_IN, 'Incoming'),
        (DIRECTION_OUT, 'Outgoing'),
    ]

    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'
    STATUS_RECEIVED = 'received'
    STATUS_CHOICES = [
        (STATUS_SENT, 'Sent'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_RECEIVED, 'Received'),
    ]

    # What triggered the message, so admins can filter e.g. only lead alerts.
    CATEGORY_CHOICES = [
        ('bot', 'Bot conversation'),
        ('lead_alert', 'Lead alert'),
        ('approval', 'Approval notice'),
        ('rejection', 'Rejection notice'),
        ('welcome', 'Welcome / credentials'),
        ('admin_test', 'Admin test message'),
        ('rate_limit', 'Rate-limit warning'),
        ('simulator', 'Simulator'),
    ]

    # Null for messages sent to numbers that never chatted with the bot (e.g. lead alerts).
    session = models.ForeignKey(
        WaBotSession,
        on_delete=models.CASCADE,
        related_name='message_logs',
        db_constraint=False,
        null=True,
        blank=True,
    )
    phone_number = models.CharField(max_length=20, blank=True, default='', db_index=True)
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='bot', db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_SENT, db_index=True)
    error = models.CharField(max_length=500, blank=True, default='')
    content = models.TextField(help_text='Message text content')
    state_at_time = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='Bot state when this message was processed',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'wa_bot_message_logs'
        ordering = ['created_at']
        verbose_name = 'WhatsApp Bot Message Log'
        verbose_name_plural = 'WhatsApp Bot Message Logs'

    def __str__(self):
        return f"[{self.direction}/{self.status}] {self.phone_number} @ {self.created_at}"
