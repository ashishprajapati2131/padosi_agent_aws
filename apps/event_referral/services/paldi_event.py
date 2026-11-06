from datetime import date

from apps.agents.models import Event
from apps.event_referral.constants import PALDI_EVENT_NAME


def get_or_create_paldi_event():
    """Ensure the admin `events` row used for event_id filters exists (id cached).

    The id lives only in the shared cache: a module-level copy outlived deleted rows
    (and test rollbacks) and cost an extra lookup without saving one."""
    from django.core.cache import cache
    cached_id = cache.get('paldi_event_row_id')
    if cached_id:
        try:
            return Event.objects.get(id=cached_id)
        except Event.DoesNotExist:
            pass

    event, _ = Event.objects.get_or_create(
        name=PALDI_EVENT_NAME,
        defaults={
            'description': 'Paldi referral challenge — agents register without payment and refer paying agents.',
            'event_date': date.today(),
        },
    )
    try:
        cache.set('paldi_event_row_id', event.id, timeout=86400)
    except Exception:
        pass
    return event


