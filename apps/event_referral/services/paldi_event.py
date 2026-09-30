from datetime import date

from apps.agents.models import Event
from apps.event_referral.constants import PALDI_EVENT_NAME


_CACHED_EVENT_ID = None


def get_or_create_paldi_event():
    """Ensure the admin `events` row used for event_id filters exists (cached)."""
    global _CACHED_EVENT_ID
    if _CACHED_EVENT_ID:
        try:
            return Event.objects.get(id=_CACHED_EVENT_ID)
        except Event.DoesNotExist:
            _CACHED_EVENT_ID = None

    from django.core.cache import cache
    cached_id = cache.get('paldi_event_row_id')
    if cached_id:
        try:
            event = Event.objects.get(id=cached_id)
            _CACHED_EVENT_ID = event.id
            return event
        except Event.DoesNotExist:
            pass

    event, _ = Event.objects.get_or_create(
        name=PALDI_EVENT_NAME,
        defaults={
            'description': 'Paldi referral challenge — agents register without payment and refer paying agents.',
            'event_date': date.today(),
        },
    )
    _CACHED_EVENT_ID = event.id
    try:
        cache.set('paldi_event_row_id', event.id, timeout=86400)
    except Exception:
        pass
    return event


def assign_paldi_event_to_agent(agent):
    if not agent:
        return
    event = get_or_create_paldi_event()
    if agent.event_id != event.id:
        agent.event_id = event.id
        agent.save(update_fields=['event_id', 'updated_at'])
