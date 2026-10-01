"""Subscription expiry, behind an admin switch (default OFF).

With "Enforce subscription expiry" OFF (the default) nothing changes: a
completed payment keeps dashboard access and directory listing forever, as
before. With it ON:
  * a paid subscription counts only until its expires_at (rows without an
    expiry date, e.g. old imports, are treated as not expiring);
  * agents whose every paid subscription has expired leave the directory and
    are sent to /chooseplan/ to renew (the payment gate already does this);
  * `manage.py expire_subscriptions` marks expired rows and lists those due.
Owner decision 2026-10-01: build it, keep it switched off until announced.
"""
from datetime import datetime

from django.db.models import Exists, OuterRef, Q

SETTING_KEY = 'subscription_expiry_enforced'


def expiry_enforced():
    from apps.home.models import SiteSetting
    value = SiteSetting.get_value(SETTING_KEY, '0')
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def still_valid_q(now=None):
    """Q for subscriptions whose paid period has not ended."""
    now = now or datetime.now()
    return Q(expires_at__isnull=True) | Q(expires_at__gt=now)


def exclude_expired_agents(agent_qs):
    """Drop agents who paid but whose every paid subscription has expired."""
    if not expiry_enforced():
        return agent_qs
    from apps.agents.models import AgentSubscription
    paid = AgentSubscription.objects.filter(agent=OuterRef('pk'), payment_status='completed')
    return (agent_qs
            .annotate(_has_paid_sub=Exists(paid), _has_valid_sub=Exists(paid.filter(still_valid_q())))
            .exclude(_has_paid_sub=True, _has_valid_sub=False))
