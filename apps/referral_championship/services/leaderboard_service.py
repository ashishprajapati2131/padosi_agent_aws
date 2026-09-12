import logging
from django.core.cache import cache
from django.db.models import Count, Q
from django.utils import timezone
from apps.referral_championship.models import (
    ChampionshipCampaign,
    ChampionshipParticipant,
    ChampionshipReferral,
    ChampionshipLeaderboardCache,
)

logger = logging.getLogger(__name__)

CACHE_KEY_LEADERBOARD = 'championship_leaderboard_all'


def refresh_leaderboard_cache(campaign=None):
    """
    Recalculate ranks and update leaderboard cache table.
    Ranking criteria:
    1. qualifying_referrals_count DESC
    2. last_qualification_time ASC (earlier server timestamp wins tie)
    """
    if not campaign:
        campaign = ChampionshipCampaign.get_current()
    if not campaign:
        return

    participants = ChampionshipParticipant.objects.filter(
        campaign=campaign,
        is_fraud_blocked=False
    ).order_by('-qualifying_referrals_count', 'last_qualification_time', 'created_at')

    rank = 1
    cache_entries = []
    for p in participants:
        p.current_rank = rank
        p.save(update_fields=['current_rank'])

        ChampionshipLeaderboardCache.objects.update_or_create(
            campaign=campaign,
            participant=p,
            defaults={
                'rank': rank,
                'referral_count': p.qualifying_referrals_count,
                'tie_breaker_ts': p.last_qualification_time or p.created_at
            }
        )
        rank += 1

    cache.delete(CACHE_KEY_LEADERBOARD)


def get_leaderboard_data(campaign=None, limit=50):
    """Fetch Top 50 leaderboard with agent display details."""
    if not campaign:
        campaign = ChampionshipCampaign.get_current()
    if not campaign:
        return []

    entries = ChampionshipLeaderboardCache.objects.filter(
        campaign=campaign
    ).select_related('participant', 'participant__agent').order_by('rank')[:limit]

    results = []
    for entry in entries:
        agent = entry.participant.agent
        profile = agent.get_primary_profile() if hasattr(agent, 'get_primary_profile') else None
        
        city = 'India'
        try:
            if hasattr(agent, 'serviceableCities'):
                c = agent.serviceableCities.first()
                if c and getattr(c, 'name', None):
                    city = c.name
        except Exception:
            pass
        city = city.title()
        name = agent.fullname or f"Agent #{agent.id}"
        # Privacy: show initials or first name + initial
        parts = name.split()
        masked_name = f"{parts[0]} {parts[1][0]}." if len(parts) > 1 else name

        results.append({
            'rank': entry.rank,
            'agent_name': masked_name,
            'city': city,
            'referral_count': entry.referral_count,
            'referral_id': entry.participant.referral_id,
        })
    return results


def get_campaign_aggregate_stats(campaign=None):
    """Return live dashboard aggregate metrics."""
    if not campaign:
        campaign = ChampionshipCampaign.get_current()
    if not campaign:
        return {
            'total_participants': 0,
            'total_paid': 0,
            'total_qualified': 0,
            'total_referrals': 0,
        }

    total_participants = ChampionshipParticipant.objects.filter(campaign=campaign).count()
    total_paid = ChampionshipReferral.objects.filter(
        campaign=campaign,
        registration_state__in=['paid', 'active']
    ).count()
    total_qualified = ChampionshipReferral.objects.filter(
        campaign=campaign,
        is_qualifying=True
    ).count()
    total_referrals = ChampionshipReferral.objects.filter(campaign=campaign).count()

    return {
        'total_participants': total_participants,
        'total_paid': total_paid,
        'total_qualified': total_qualified,
        'total_referrals': total_referrals,
    }
