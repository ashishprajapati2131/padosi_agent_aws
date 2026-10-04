from django.db import models


class GoogleReviewConfig(models.Model):
    """
    Per-agent Google Review settings and cached reviews.
    Allows agents to display their Google reviews on their public profile
    and configure their Google review redirect URL.
    """
    agent = models.OneToOneField(
        'agents.Agent',
        on_delete=models.CASCADE,
        related_name='google_review_config',
        db_constraint=False,
    )
    is_enabled = models.BooleanField(
        default=False,
        help_text='Agent-level ON/OFF switch for Google Reviews display'
    )
    google_review_url = models.URLField(
        max_length=500,
        blank=True,
        default='',
        help_text='Direct URL to write a review on Google'
    )
    google_rating = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
        help_text='Overall Google Rating, e.g. 4.8'
    )
    google_review_count = models.IntegerField(
        default=0,
        help_text='Total count of reviews on Google'
    )
    google_place_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Business or Agent name as listed on Google'
    )
    # Stored reviews format:
    # [{"author": "...", "rating": 5, "text": "...", "time": "2 weeks ago"}]
    cached_reviews = models.JSONField(
        default=list,
        blank=True,
        help_text='Up to 5 featured Google reviews entered by agent'
    )
    google_review_clicks = models.IntegerField(
        default=0,
        help_text='Total clicks on Review on Google CTA'
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'agent_google_review_configs'
        managed = True
        verbose_name = 'Google Review Config'
        verbose_name_plural = 'Google Review Configs'

    def __str__(self):
        agent_name = getattr(self.agent, 'fullname', f'Agent #{self.agent_id}')
        status = 'Enabled' if self.is_enabled else 'Disabled'
        return f'{agent_name} - Google Reviews ({status})'
