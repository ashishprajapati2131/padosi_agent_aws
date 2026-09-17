import logging
from django.utils import timezone
from apps.referral_championship.models import (
    ChampionshipCampaign,
    ChampionshipParticipant,
    ChampionshipRewardSlab,
    ChampionshipRewardClaim,
)

logger = logging.getLogger(__name__)


def evaluate_participant_rewards(participant):
    """
    Evaluate and auto-unlock milestone rewards for a participant based on qualifying referrals.
    Cumulative except travel rewards.
    """
    if not participant:
        return []

    campaign = participant.campaign
    slabs = ChampionshipRewardSlab.objects.filter(campaign=campaign, is_active=True).order_by('threshold')
    count = participant.qualifying_referrals_count

    unlocked_claims = []
    for slab in slabs:
        # Handle Top 3 check separately during final leaderboard
        if slab.threshold >= 900:
            continue

        if count >= slab.threshold:
            claim, created = ChampionshipRewardClaim.objects.get_or_create(
                participant=participant,
                reward_slab=slab,
                defaults={'status': 'unlocked'}
            )
            if created or claim.status == 'locked':
                claim.status = 'unlocked'
                claim.save()
            unlocked_claims.append(claim)

    return unlocked_claims


def format_inr(val):
    if val is None or val == '':
        return ""
    try:
        val_int = int(float(val))
    except (TypeError, ValueError):
        return ""
    s = str(val_int)
    if len(s) <= 3:
        return f"₹{s}"
    last3 = s[-3:]
    rest = s[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return f"₹{','.join(parts)},{last3}"


def get_reward_image(reward_type, threshold=None):
    """Map reward_type or threshold to static asset image path from banner."""
    if threshold == 5 or reward_type in ('membership_fee_back', 'cashback', 'voucher'):
        return 'championship/step-1-feeback.png'
    elif threshold == 10 or reward_type == 'plan_upgrade':
        return 'championship/step-2-profree.png'
    elif threshold == 25 or reward_type == 'silver':
        return 'championship/step-3-silver.png'
    elif threshold == 50 or reward_type == 'gold':
        return 'championship/step-4-gold.png'
    elif threshold == 100 or reward_type == 'domestic_trip':
        return 'championship/step-5-domestictrip.png'
    elif threshold == 200 or reward_type == 'international_trip':
        return 'championship/step-6-intltrip.png'
    elif (threshold and threshold >= 900) or reward_type == 'family_trip':
        return 'championship/step-7-topchampions.png'
    return 'championship/step-1-feeback.png'



def get_participant_roadmap(participant):
    """
    Build the visual reward roadmap for the participant dashboard:
    Status for each tier:
    - locked
    - unlocked (ready to claim)
    - processing / approved / dispatched / delivered / redeemed
    """
    campaign = participant.campaign if participant else ChampionshipCampaign.get_current()
    slabs = ChampionshipRewardSlab.objects.filter(campaign=campaign, is_active=True).order_by('threshold', 'order')
    
    count = participant.qualifying_referrals_count if participant else 0
    claims_by_slab = {}
    if participant:
        for c in ChampionshipRewardClaim.objects.filter(participant=participant).select_related('reward_slab'):
            claims_by_slab[c.reward_slab_id] = c

    roadmap = []
    next_reward = None
    referrals_needed = 0
    prev_threshold = 0

    # First find the active target
    for slab in slabs:
        if count < slab.threshold and next_reward is None and slab.threshold < 900:
            next_reward = slab
            referrals_needed = max(0, slab.threshold - count)

    idx = 1
    for slab in slabs:
        is_reached = count >= slab.threshold if slab.threshold < 900 else False
        claim = claims_by_slab.get(slab.id)
        
        status = 'locked'
        if claim:
            status = claim.status
        elif is_reached:
            status = 'unlocked'

        is_unlocked = bool(is_reached or status in ['unlocked', 'claimed', 'approved', 'dispatched', 'delivered', 'redeemed'])
        is_current_target = bool(next_reward and slab.id == next_reward.id)

        # Progress within this milestone tier
        if is_unlocked:
            progress_percent = 100
        elif is_current_target:
            span = max(1, slab.threshold - prev_threshold)
            completed_in_span = max(0, count - prev_threshold)
            progress_percent = min(99, int((completed_in_span / span) * 100))
        else:
            progress_percent = 0

        prev_threshold = slab.threshold if slab.threshold < 900 else prev_threshold

        roadmap.append({
            'slab': slab,
            'index': idx,
            'is_reached': is_reached,
            'is_unlocked': is_unlocked,
            'is_current_target': is_current_target,
            'progress_percent': progress_percent,
            'referrals_needed': max(0, slab.threshold - count),
            'claim': claim,
            'status': status,
            'threshold': slab.threshold,
            'title': slab.title,
            'description': slab.description,
            'value': float(slab.value) if slab.value is not None else None,
            'value_formatted': format_inr(slab.value),
            'reward_type': slab.reward_type,
            'image_path': get_reward_image(slab.reward_type, slab.threshold),
            'badge_icon': slab.badge_icon,
            'dispatch_date': str(slab.dispatch_date_default) if slab.dispatch_date_default else None,
        })
        idx += 1

    return {
        'roadmap': roadmap,
        'count': count,
        'next_reward': next_reward.title if next_reward else ("Grand Family Trip (Top 3)" if count >= 200 else "All Slabs Achieved!"),
        'referrals_needed': referrals_needed,
    }

