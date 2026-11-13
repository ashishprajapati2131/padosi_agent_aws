import logging
from django.db import transaction
from django.utils import timezone
from apps.referral_championship.models import (
    ChampionshipRewardClaim,
    ChampionshipCampaign,
    ChampionshipParticipant,
    ChampionshipReferral,
    ChampionshipAuditLog,
)
from apps.referral_championship.services.attribution_service import (
    validate_referral_integrity,
)

logger = logging.getLogger(__name__)


def _schedule_leaderboard_refresh(campaign):
    """Re-rank after the surrounding (payment) transaction commits.

    The refresh writes every participant row; doing it while the referrer row
    lock is held deadlocked, and the savepoint rollback dropped the credit.
    """

    def _run():
        from apps.referral_championship.services.leaderboard_service import (
            refresh_leaderboard_cache,
        )

        try:
            refresh_leaderboard_cache(campaign)
        except Exception:
            logger.exception(
                "Championship leaderboard refresh failed for campaign %s", campaign.pk
            )

    from django.core.cache import cache

    # Audit CH17: at most one re-rank per 30s per campaign. A skipped one marks the board
    # dirty; the next payment or leaderboard read after the window refreshes it.
    if not cache.add(f"lb_refresh_{campaign.pk}", 1, 30):
        cache.set(f"lb_dirty_{campaign.pk}", 1, None)
        return
    cache.delete(f"lb_dirty_{campaign.pk}")
    transaction.on_commit(_run)


def _championship_participant_for_event_code(code, campaign):
    """Championship participant of the Paldi (EV-) challenger owning `code`.

    Owner decision 2026-10-02: a Paldi challenger's paid referrals also
    count in the championship (road, slabs, claims, leaderboard), during
    and after the 48-hour challenge.
    """
    from apps.event_referral.models import EventReferralParticipant
    from apps.referral_championship.services.attribution_service import (
        get_or_create_participant,
    )

    event_participant = (
        EventReferralParticipant.objects.select_related("agent")
        .filter(referral_code=code)
        .first()
    )
    if not event_participant or not event_participant.agent_id:
        return None
    return get_or_create_participant(event_participant.agent, campaign)


def process_championship_qualification(new_agent, subscription):
    """
    Process server-side qualification when an agent successfully pays for a plan.
    Adds exactly 1 qualifying referral to the referrer.
    No referral multiplier.
    """
    if not new_agent or not subscription or subscription.payment_status != "completed":
        return False

    campaign = ChampionshipCampaign.get_current()
    if not campaign or campaign.status not in ["live", "scheduled"]:
        return False

    # Check if campaign deadline passed
    if timezone.now() > campaign.end_date:
        logger.info(
            f"Campaign deadline passed. Qualifying referral skipped for agent {new_agent.id}"
        )
        return False

    # Find existing attribution record or retrieve from agent.referred_by_code
    referral_rec = ChampionshipReferral.objects.filter(
        referred_agent=new_agent, campaign=campaign
    ).first()

    referrer_participant = None

    if referral_rec:
        referrer_participant = referral_rec.referrer
    else:
        # Check if agent was referred via championship code
        code_cand = (new_agent.referred_by_code or "").strip().upper()
        if code_cand.startswith("PA-"):
            referrer_participant = ChampionshipParticipant.objects.filter(
                referral_id=code_cand, campaign=campaign
            ).first()
        elif code_cand.startswith("EV-"):
            referrer_participant = _championship_participant_for_event_code(
                code_cand, campaign
            )

    if not referrer_participant:
        return False

    # Verify fraud checks
    is_valid, reason = validate_referral_integrity(referrer_participant, new_agent)
    if not is_valid:
        logger.warning(
            f"Championship qualification blocked for {new_agent.id}: {reason}"
        )
        if referral_rec:
            referral_rec.registration_state = "fraud_blocked"
            referral_rec.fraud_flag = True
            referral_rec.save()
        return False

    with transaction.atomic():
        # Serialise concurrent qualifications of the same referrer: two
        # referrals paying at once both wrote N+1 instead of N+2.
        referrer_participant = ChampionshipParticipant.objects.select_for_update().get(
            pk=referrer_participant.pk
        )
        if not referral_rec:
            # Look again under the lock: a parallel callback/webhook may have created it (audit CH4).
            referral_rec = ChampionshipReferral.objects.filter(
                referred_agent=new_agent, campaign=campaign
            ).first()
        if not referral_rec:
            referral_rec = ChampionshipReferral.objects.create(
                campaign=campaign,
                referrer=referrer_participant,
                referred_agent=new_agent,
                referral_id=referrer_participant.referral_id,
                registration_state="paid",
                is_qualifying=True,
                qualified_at=timezone.now(),
            )
        else:
            if not referral_rec.is_qualifying:
                referral_rec.registration_state = "paid"
                referral_rec.is_qualifying = True
                referral_rec.qualified_at = timezone.now()
                referral_rec.save()

        # Recount exact qualifying referrals for referrer (only verified + paid)
        # Locking read: sees other referrals committed while we waited.
        actual_count = len(
            ChampionshipReferral.objects.select_for_update()
            .filter(
                referrer=referrer_participant,
                is_qualifying=True,
                registration_state__in=["paid", "active"],
            )
            .values_list("id", flat=True)
        )

        referrer_participant.qualifying_referrals_count = actual_count
        referrer_participant.last_qualification_time = timezone.now()
        referrer_participant.save(
            update_fields=["qualifying_referrals_count", "last_qualification_time"]
        )

        # Auto evaluate reward milestones
        from apps.referral_championship.services.reward_engine import (
            evaluate_participant_rewards,
        )

        evaluate_participant_rewards(referrer_participant)

        # Update leaderboard ranks
        _schedule_leaderboard_refresh(campaign)

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
        referred_agent=agent, campaign=campaign, is_qualifying=True
    ).first()

    if not referral_rec:
        return False

    referrer = referral_rec.referrer
    old_count = referrer.qualifying_referrals_count

    with transaction.atomic():
        referrer = ChampionshipParticipant.objects.select_for_update().get(pk=referrer.pk)
        referral_rec.is_qualifying = False
        referral_rec.registration_state = (
            "refunded" if reason == "refund" else "cancelled"
        )
        referral_rec.save()

        # Recount
        actual_count = ChampionshipReferral.objects.filter(
            referrer=referrer,
            is_qualifying=True,
            registration_state__in=["paid", "active"],
        ).count()

        referrer.qualifying_referrals_count = actual_count
        referrer.save(update_fields=["qualifying_referrals_count"])

        # Withdraw in-flight claims for slabs the agent no longer qualifies for. A paid-out claim
        # (dispatched / delivered / redeemed) is not touched — those are real money (audit CH3).
        ChampionshipRewardClaim.objects.filter(
            participant=referrer,
            reward_slab__threshold__gt=actual_count,
            status__in=("unlocked", "verification", "approved", "processing"),
        ).update(status="cancelled")

        # Audit log
        ChampionshipAuditLog.objects.create(
            campaign=campaign,
            action=f"Referral Disqualified: {reason}",
            old_value={
                "referrer": referrer.referral_id,
                "count": old_count,
                "referred_agent": agent.id,
            },
            new_value={
                "referrer": referrer.referral_id,
                "count": actual_count,
                "status": referral_rec.registration_state,
            },
            reason=f"Agent payment was {reason}ed.",
        )

        _schedule_leaderboard_refresh(campaign)

    logger.info(
        f"Reverted qualification for referrer {referrer.referral_id}. Count adjusted from {old_count} to {actual_count}."
    )
    return True
