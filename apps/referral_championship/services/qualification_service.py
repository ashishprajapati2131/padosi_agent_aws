import logging
from django.db import transaction
from django.utils import timezone
from apps.referral_championship.models import (
    ChampionshipCampaign,
    ChampionshipParticipant,
    ChampionshipReferral,
    ChampionshipAuditLog,
)
from apps.referral_championship.services.attribution_service import validate_referral_integrity

logger = logging.getLogger(__name__)


def process_championship_qualification(new_agent, subscription):
    """
    Process server-side qualification when an agent successfully pays for a plan.
    Adds exactly 1 qualifying referral to the referrer.
    No referral multiplier.
    """
    if not new_agent or not subscription or subscription.payment_status != 'completed':
        return False

    campaign = ChampionshipCampaign.get_current()
    if not campaign or campaign.status not in ['live', 'scheduled']:
        return False

    # Check if campaign deadline passed
    if timezone.now() > campaign.end_date:
        logger.info(f"Campaign deadline passed. Qualifying referral skipped for agent {new_agent.id}")
        return False

    # Find existing attribution record or retrieve from agent.referred_by_code
    referral_rec = ChampionshipReferral.objects.filter(
        referred_agent=new_agent,
        campaign=campaign
    ).first()

    referrer_participant = None

    if referral_rec:
        referrer_participant = referral_rec.referrer
    else:
        # Check if agent was referred via championship code
        code_cand = (new_agent.referred_by_code or '').strip().upper()
        if code_cand.startswith('PA-'):
            referrer_participant = ChampionshipParticipant.objects.filter(
                referral_id=code_cand,
                campaign=campaign
            ).first()

    if not referrer_participant:
        return False

    # Verify fraud checks
    is_valid, reason = validate_referral_integrity(referrer_participant, new_agent)
    if not is_valid:
        logger.warning(f"Championship qualification blocked for {new_agent.id}: {reason}")
        if referral_rec:
            referral_rec.registration_state = 'fraud_blocked'
            referral_rec.fraud_flag = True
            referral_rec.save()
        return False

    with transaction.atomic():
        if not referral_rec:
            referral_rec = ChampionshipReferral.objects.create(
                campaign=campaign,
                referrer=referrer_participant,
                referred_agent=new_agent,
                referral_id=referrer_participant.referral_id,
                registration_state='paid',
                is_qualifying=True,
                qualified_at=timezone.now()
            )
        else:
            if not referral_rec.is_qualifying:
                referral_rec.registration_state = 'paid'
                referral_rec.is_qualifying = True
                referral_rec.qualified_at = timezone.now()
                referral_rec.save()

        # Recount exact qualifying referrals for referrer (only verified + paid)
        actual_count = ChampionshipReferral.objects.filter(
            referrer=referrer_participant,
            is_qualifying=True,
            registration_state__in=['paid', 'active']
        ).count()

        referrer_participant.qualifying_referrals_count = actual_count
        referrer_participant.last_qualification_time = timezone.now()
        referrer_participant.save(update_fields=['qualifying_referrals_count', 'last_qualification_time'])

        # Auto evaluate reward milestones
        from apps.referral_championship.services.reward_engine import evaluate_participant_rewards
        evaluate_participant_rewards(referrer_participant)

        # Update leaderboard ranks
        from apps.referral_championship.services.leaderboard_service import refresh_leaderboard_cache
        refresh_leaderboard_cache(campaign)

    logger.info(
        f"Championship qualification complete: Referrer {referrer_participant.referral_id} "
        f"now has {actual_count} qualifying referrals (Agent #{new_agent.id} joined)."
    )
    return True


def revert_championship_qualification(agent, reason="refund"):
    """
    If a referral becomes refunded, cancelled, chargeback, or fraudulent,
    automatically remove that referral from the qualifying count and record an audit log.
    """
    campaign = ChampionshipCampaign.get_current()
    if not campaign:
        return False

    referral_rec = ChampionshipReferral.objects.filter(
        referred_agent=agent,
        campaign=campaign,
        is_qualifying=True
    ).first()

    if not referral_rec:
        return False

    referrer = referral_rec.referrer
    old_count = referrer.qualifying_referrals_count

    with transaction.atomic():
        referral_rec.is_qualifying = False
        referral_rec.registration_state = 'refunded' if reason == 'refund' else 'cancelled'
        referral_rec.save()

        # Recount
        actual_count = ChampionshipReferral.objects.filter(
            referrer=referrer,
            is_qualifying=True,
            registration_state__in=['paid', 'active']
        ).count()

        referrer.qualifying_referrals_count = actual_count
        referrer.save(update_fields=['qualifying_referrals_count'])

        # Audit log
        ChampionshipAuditLog.objects.create(
            campaign=campaign,
            action=f"Referral Disqualified: {reason}",
            old_value={"referrer": referrer.referral_id, "count": old_count, "referred_agent": agent.id},
            new_value={"referrer": referrer.referral_id, "count": actual_count, "status": referral_rec.registration_state},
            reason=f"Agent payment was {reason}ed."
        )

        from apps.referral_championship.services.leaderboard_service import refresh_leaderboard_cache
        refresh_leaderboard_cache(campaign)

    logger.info(f"Reverted qualification for referrer {referrer.referral_id}. Count adjusted from {old_count} to {actual_count}.")
    return True
