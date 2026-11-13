"""Public ranking for Paldi / EV- challengers by counted paid referrals."""
from django.db.models import Sum
from django.utils.text import capfirst

from apps.event_referral.models import EventReferralCampaign, EventReferralParticipant


def _agent_city(agent):
    if not agent:
        return ''
    try:
        # .all() uses the prefetch; .first() re-queried per row. City has no Meta.ordering, so pk order == .first().
        city = min(agent.serviceableCities.all(), key=lambda c: c.pk, default=None)
        if city and getattr(city, 'name', None):
            return capfirst(str(city.name).strip())
    except Exception:
        pass
    state = (getattr(agent, 'state', None) or '').strip()
    return capfirst(state) if state else 'India'


def _agent_display_name(agent):
    if not agent:
        return 'Agent'
    name = (getattr(agent, 'fullname', None) or '').strip()
    return name or f"Agent #{agent.id}"


def _agent_initials(name):
    parts = (name or 'AG').split()
    if len(parts) >= 2:
        return (parts[0][:1] + parts[1][:1]).upper()
    return (parts[0][:2] if parts else 'AG').upper()


def build_leaderboard_rows(participants, *, photo_url_builder=None):
    rows = []
    rank = 0
    for participant in participants:
        agent = participant.agent
        if not agent:
            continue
        rank += 1
        name = _agent_display_name(agent)
        photo_url = ''
        if photo_url_builder:
            try:
                profile = agent.get_primary_profile()
                if profile and getattr(profile, 'profile_photo_path', None):
                    photo_url = photo_url_builder(profile) or ''
            except Exception:
                photo_url = ''
        rows.append(
            {
                'rank': rank,
                'participant_id': participant.id,
                'agent_id': agent.id,
                'name': name,
                'initials': _agent_initials(name),
                'city': _agent_city(agent),
                'paid_count': int(participant.paid_count or 0),
                'required': int(participant.required_paid_referrals or 5),
                'status': participant.status,
                'referral_code': participant.referral_code,
                'photo_url': photo_url,
            }
        )
    return rows


def get_public_leaderboard_payload(*, limit=50, photo_url_builder=None):
    from django.core.cache import cache
    cache_key = f'public_leaderboard_payload_{limit}'
    if not photo_url_builder:
        try:
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        except Exception:
            pass

    campaign = EventReferralCampaign.get_current()
    if not campaign:
        return {
            'campaign': None,
            'leaderboard': [],
            'top_three': [],
            'rest': [],
            'stats': {'total_agents': 0, 'total_paid_referrals': 0, 'top_paid': 0},
        }

    # Audit CH9: no per-referral entries — the page never rendered them and they carried contacts.
    base_qs = (
        EventReferralParticipant.objects.filter(campaign=campaign)
        .select_related('agent', 'agent__profile')
        .prefetch_related('agent__serviceableCities')
        .order_by('-paid_count', '-updated_at', '-registered_at')
    )
    stats = base_qs.aggregate(total_paid=Sum('paid_count'))
    total_agents = base_qs.count()
    total_paid = int(stats.get('total_paid') or 0)
    top_row = base_qs.first()
    top_paid = int(top_row.paid_count) if top_row else 0

    rows = build_leaderboard_rows(base_qs[:limit], photo_url_builder=photo_url_builder)
    result = {
        'campaign': campaign,
        'leaderboard': rows,
        'top_three': rows[:3],
        'rest': rows[3:],
        'stats': {
            'total_agents': total_agents,
            'total_paid_referrals': total_paid,
            'top_paid': top_paid,
        },
    }
    if not photo_url_builder:
        try:
            cache.set(cache_key, result, timeout=5)
        except Exception:
            pass
    return result
