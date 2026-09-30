"""Resolve a one-time app upgrade link without burning it on a page view."""
from datetime import datetime

from apps.agents.models import PlanUpgradeHandoff
from plan_upgrade_handoff import (
    hash_handoff_token,
    normalize_upgrade_slug,
    upgrade_target_allowed,
)


def peek_plan_upgrade_handoff(raw_token):
    """
    Return a valid unused token row without marking it used.

    A browser prefetch of the link must not burn the token. The token is
    marked used only after the website login succeeds.
    """
    raw = (raw_token or '').strip()
    if not raw or len(raw) > 128:
        return None
    now = datetime.now()
    return (
        PlanUpgradeHandoff.objects.filter(
            token_hash=hash_handoff_token(raw),
            used_at__isnull=True,
            expires_at__gt=now,
        )
        .select_related('agent')
        .first()
    )


def mark_plan_upgrade_handoff_used(row):
    """Mark the token used. Returns False when another request already did."""
    if row is None or not row.pk:
        return False
    now = datetime.now()
    updated = PlanUpgradeHandoff.objects.filter(
        pk=row.pk,
        used_at__isnull=True,
        expires_at__gt=now,
    ).update(used_at=now)
    return updated == 1


def dashboard_upgrade_slug(agent, raw_upgrade):
    """Plan slug the dashboard should open, or '' when the query is not an upgrade."""
    if not agent:
        return ''
    target = normalize_upgrade_slug(raw_upgrade)
    if not upgrade_target_allowed(getattr(agent, 'plan_type', ''), target):
        return ''
    return target
