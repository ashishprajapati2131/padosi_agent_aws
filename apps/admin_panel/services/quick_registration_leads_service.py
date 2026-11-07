"""Write flows for admin quick-registration leads (views/quick_registration_leads.py)."""

import logging

from django.utils import timezone

from apps.admin_panel.models import RegistrationLead

# Same logger name as before the move, so log routing/filters are unchanged.
logger = logging.getLogger("apps.admin_panel.views.quick_registration_leads")

ABANDON_AFTER_DAYS = 30


def sync_active_agent_conversions():
    """Ensure any leads with matching active agents are marked converted and removed from open list."""
    try:
        from apps.agents.models import Agent
        active_phones = set(
            Agent.objects.filter(status='active').exclude(mobile='').values_list('mobile', flat=True)
        )
        if active_phones:
            clean_phones = {p[-10:] for p in active_phones if len(p) >= 10}
            RegistrationLead.objects.filter(
                phone__in=clean_phones,
            ).exclude(status=RegistrationLead.STATUS_CONVERTED).update(
                status=RegistrationLead.STATUS_CONVERTED,
                converted_at=timezone.now(),
                form_filled=True,
                payment_status=RegistrationLead.PAYMENT_COMPLETED,
            )
    except Exception as e:
        logger.warning(f"Error syncing active agent conversions: {e}")


def abandon_stale_leads():
    """Quiet leads that never finished the form are marked abandoned after 30 days."""
    cutoff = timezone.now() - timezone.timedelta(days=ABANDON_AFTER_DAYS)
    RegistrationLead.objects.filter(
        status__in=(
            RegistrationLead.STATUS_QUICK_REGISTERED,
            RegistrationLead.STATUS_FORM_STARTED,
        ),
        updated_at__lt=cutoff,
    ).update(status=RegistrationLead.STATUS_ABANDONED)


def delete_lead(lead):
    lead.delete()
