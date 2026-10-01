import logging

from django.db.models import F

from apps.event_referral.models import EventReferralCampaign, EventReferralParticipant

logger = logging.getLogger(__name__)

SESSION_PAGE_SECONDS_KEY = 'event_referral_page_active_seconds'


def increment_registration_link_open_count(campaign_id):
    from apps.event_referral.services.db_utils import run_with_db_retry
    from apps.event_referral.services.schema_compat import ensure_event_referral_metrics_schema

    ensure_event_referral_metrics_schema(log_errors=False)

    def _increment():
        EventReferralCampaign.objects.filter(pk=campaign_id).update(
            registration_link_open_count=F('registration_link_open_count') + 1,
        )

    run_with_db_retry(_increment)


def accumulate_event_page_active_seconds(request, delta_seconds):
    """Track visible time on event registration / dashboard (session + participant row)."""
    from apps.event_referral.services.schema_compat import ensure_event_referral_metrics_schema

    ensure_event_referral_metrics_schema(log_errors=False)
    try:
        delta = int(delta_seconds)
    except (TypeError, ValueError):
        return 0
    delta = max(0, min(delta, 120))
    if delta <= 0:
        return 0

    session_total = int(request.session.get(SESSION_PAGE_SECONDS_KEY, 0) or 0) + delta
    request.session[SESSION_PAGE_SECONDS_KEY] = session_total
    request.session.modified = True

    if not request.user.is_authenticated:
        return delta

    try:
        from apps.agents.services.account_auth import resolve_agent_for_user

        agent = resolve_agent_for_user(request.user)
        if not agent:
            return delta
        updated = EventReferralParticipant.objects.filter(agent=agent).update(
            page_active_seconds=F('page_active_seconds') + delta,
        )
        if not updated:
            return delta
    except Exception as exc:
        logger.warning('Event page time update failed: %s', exc)
    return delta


def flush_session_page_seconds_to_participant(request, participant):
    """Move pre-login session time onto the participant row once at signup."""
    if not participant:
        return
    pending = int(request.session.pop(SESSION_PAGE_SECONDS_KEY, 0) or 0)
    request.session.modified = True
    if pending <= 0:
        return
    EventReferralParticipant.objects.filter(pk=participant.pk).update(
        page_active_seconds=F('page_active_seconds') + pending,
    )
