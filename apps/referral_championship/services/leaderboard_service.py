import logging
from django.core.cache import cache
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
    # Admin froze the leaderboard: keep ranks and rows exactly as they are.
    if ChampionshipLeaderboardCache.objects.filter(campaign=campaign, is_frozen=True).exists():
        return

    participants = ChampionshipParticipant.objects.filter(
        campaign=campaign,
        is_fraud_blocked=False
    ).order_by('-qualifying_referrals_count', 'last_qualification_time', 'created_at')

    existing = {
        row.participant_id: row
        for row in ChampionshipLeaderboardCache.objects.filter(campaign=campaign)
    }
    now = timezone.now()
    changed_participants, cache_updates, cache_creates = [], [], []
    for rank, p in enumerate(participants, start=1):
        if p.current_rank != rank:
            p.current_rank = rank
            changed_participants.append(p)
        tie_breaker_ts = p.last_qualification_time or p.created_at
        row = existing.get(p.pk)
        if row is None:
            cache_creates.append(ChampionshipLeaderboardCache(
                campaign=campaign,
                participant=p,
                rank=rank,
                referral_count=p.qualifying_referrals_count,
                tie_breaker_ts=tie_breaker_ts,
            ))
        else:
            row.rank = rank
            row.referral_count = p.qualifying_referrals_count
            row.tie_breaker_ts = tie_breaker_ts
            row.updated_at = now  # bulk_update skips auto_now
            cache_updates.append(row)

    ChampionshipParticipant.objects.bulk_update(changed_participants, ['current_rank'], batch_size=500)
    ChampionshipLeaderboardCache.objects.bulk_update(
        cache_updates, ['rank', 'referral_count', 'tie_breaker_ts', 'updated_at'], batch_size=500
    )
    # ignore_conflicts: a concurrent refresh may have inserted the same row; both compute the same ranks.
    ChampionshipLeaderboardCache.objects.bulk_create(cache_creates, batch_size=500, ignore_conflicts=True)
    # Drop rows of participants no longer ranked (e.g. fraud-blocked since the last refresh).
    ChampionshipLeaderboardCache.objects.filter(campaign=campaign).exclude(
        participant__in=participants
    ).delete()

    cache.delete(CACHE_KEY_LEADERBOARD)


def get_leaderboard_data(campaign=None, limit=50):
    """Fetch Top 50 leaderboard with agent display details."""
    if not campaign:
        campaign = ChampionshipCampaign.get_current()
    if not campaign:
        return []
    # Audit CH17: apply a re-rank that the payment-path debounce skipped.
    if cache.get(f"lb_dirty_{campaign.pk}") and cache.add(f"lb_refresh_{campaign.pk}", 1, 30):
        cache.delete(f"lb_dirty_{campaign.pk}")
        refresh_leaderboard_cache(campaign)

    entries = ChampionshipLeaderboardCache.objects.filter(
        campaign=campaign
    ).select_related('participant', 'participant__agent').prefetch_related(
        'participant__agent__serviceableCities'
    ).order_by('rank')[:limit]

    results = []
    for entry in entries:
        try:
            participant = getattr(entry, 'participant', None)
            if not participant:
                continue
            agent = getattr(participant, 'agent', None)
            if not agent:
                continue

            city = 'India'
            try:
                if hasattr(agent, 'serviceableCities'):
                    # Same row as .first() (City has no Meta.ordering) without a query per entry.
                    c = min(agent.serviceableCities.all(), key=lambda city: city.pk, default=None)
                    if c and getattr(c, 'name', None):
                        city = c.name
            except Exception:
                pass
            city = city.title()

            raw_name = (getattr(agent, 'fullname', '') or '').strip() or f"Agent #{getattr(agent, 'id', '')}"
            parts = raw_name.split()
            if len(parts) > 1 and parts[1]:
                masked_name = f"{parts[0]} {parts[1][0]}."
            elif len(parts) > 0:
                masked_name = parts[0]
            else:
                masked_name = f"Agent #{getattr(agent, 'id', '')}"

            results.append({
                'rank': entry.rank,
                'id': participant.id,
                'agent_id': agent.id,
                'agent_name': masked_name,
                'name': masked_name,
                'city': city,
                'referral_count': entry.referral_count,
                'referrals': entry.referral_count,
                'referral_id': participant.referral_id,
            })
        except Exception as e:
            logger.warning(f"Error reading leaderboard entry #{getattr(entry, 'id', None)}: {e}")
            continue
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
