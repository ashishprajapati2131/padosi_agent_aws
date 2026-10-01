"""Evaluate deadlines, wins, blocks, and dashboard access for event referral challengers."""
import logging
from datetime import datetime

from django.db import transaction

from apps.agents.models import Agent
from apps.event_referral.models import EventReferral, EventReferralParticipant

logger = logging.getLogger(__name__)

BLOCK_MESSAGE = (
    'Your event referral challenge ended. You did not complete the required paid '
    'referrals in time. Please contact support if you need help.'
)


def get_participant_for_agent(agent):
    if not agent:
        return None
    return (
        EventReferralParticipant.objects.filter(agent=agent)
        .select_related('campaign')
        .first()
    )


def event_referral_grants_dashboard(agent):
    """Allow dashboard without Razorpay for active/won challengers and expired (locked) challengers."""
    participant = get_participant_for_agent(agent)
    if not participant:
        return False
    if participant.status in (
        EventReferralParticipant.STATUS_ACTIVE,
        EventReferralParticipant.STATUS_WON,
        EventReferralParticipant.STATUS_BLOCKED,
    ):
        return True
    return False


def prepare_event_referral_portal_state(agent):
    """
    Run expiry checks on portal page loads.
    Returns (participant, force_lock_all_features, event_referral_expired_locked).
    """
    participant = get_participant_for_agent(agent)
    if not participant:
        return None, False, False
    if participant.status == EventReferralParticipant.STATUS_ACTIVE:
        evaluate_agent(agent, block_on_expire=True)
        participant = get_participant_for_agent(agent)
    force_lock = force_lock_all_dashboard_features(participant)
    expired_locked = bool(
        participant
        and participant.status == EventReferralParticipant.STATUS_BLOCKED
        and force_lock
    )
    return participant, force_lock, expired_locked


def event_referral_expired_needs_plan_payment(agent):
    """
    True when the 48h challenge ended without a win and the agent still needs a paid plan.
    Used to allow /chooseplan/ instead of bouncing back to the locked dashboard.
    """
    participant = get_participant_for_agent(agent)
    if not participant or participant.status != EventReferralParticipant.STATUS_BLOCKED:
        return False
    from apps.agents.services.account_auth import agent_has_completed_payment

    return not agent_has_completed_payment(agent)


def event_referral_bypasses_championship_unlock(agent):
    """
    Paldi / event-registration (EV-) agents skip PA- championship profile % and review gates.
    Does not apply to normal championship-only participants.
    """
    return event_referral_grants_dashboard(agent)


def force_lock_all_dashboard_features(participant):
    """Lock dashboard after 48h expiry until the agent pays for a plan."""
    if participant is None or participant.status != EventReferralParticipant.STATUS_BLOCKED:
        return False
    from apps.agents.services.account_auth import agent_has_completed_payment

    agent = participant.agent
    if agent and agent_has_completed_payment(agent):
        return False
    return True


def event_referral_effective_plan_type(agent, participant=None):
    """
    Plan slug used for feature gates during the Paldi / event referral challenge.
    - Active (within 48h): Professional trial — same as paid Professional.
    - Won: reward plan (usually basic/starter).
    - Blocked: None (dashboard access is revoked separately).
    """
    participant = participant or get_participant_for_agent(agent)
    if not participant:
        return None
    if participant.status == EventReferralParticipant.STATUS_ACTIVE:
        return 'professional'
    if participant.status == EventReferralParticipant.STATUS_WON:
        slug = (participant.reward_plan_slug or 'basic').strip().lower() or 'basic'
        if slug in ('basic', 'starter', 'standard'):
            return 'starter'
        return slug
    return None


def _recount_paid(participant):
    return EventReferral.objects.filter(
        participant=participant,
        counts=True,
        state=EventReferral.STATE_PAID,
    ).count()


def _grant_win(participant):
    agent = participant.agent
    plan = participant.reward_plan_slug or 'basic'
    participant.status = EventReferralParticipant.STATUS_WON
    participant.won_at = datetime.now()
    participant.paid_count = _recount_paid(participant)
    participant.save(
        update_fields=['status', 'won_at', 'paid_count', 'updated_at'],
    )
    agent.status = 'pending_approval'
    agent.plan_type = plan
    agent.registration_step = max(agent.registration_step or 1, 2)
    agent.save(update_fields=['status', 'plan_type', 'registration_step', 'updated_at'])
    logger.info(
        'Event referral win: agent #%s participant %s plan=%s',
        agent.id,
        participant.referral_code,
        plan,
    )


def _block_participant(participant, reason=''):
    participant.status = EventReferralParticipant.STATUS_BLOCKED
    participant.blocked_at = datetime.now()
    participant.blocked_reason = reason or 'Deadline passed without enough paid referrals.'
    participant.save(
        update_fields=['status', 'blocked_at', 'blocked_reason', 'updated_at'],
    )
    agent = participant.agent
    if agent.status not in ('active', 'pending_approval'):
        agent.status = 'pending_payment'
        agent.save(update_fields=['status', 'updated_at'])
    logger.info(
        'Event referral blocked: agent #%s participant %s',
        agent.id,
        participant.referral_code,
    )


def evaluate_participant(participant, *, block_on_expire=True):
    """
    Check win/loss for one participant. Returns participant (refreshed) or None.
    """
    if not participant:
        return None
    with transaction.atomic():
        participant = (
            EventReferralParticipant.objects.select_for_update()
            .select_related('agent')
            .filter(pk=participant.pk)
            .first()
        )
        if not participant:
            return None
        if participant.status == EventReferralParticipant.STATUS_WON:
            return participant
        if participant.status == EventReferralParticipant.STATUS_BLOCKED:
            return participant

        participant.paid_count = _recount_paid(participant)
        participant.save(update_fields=['paid_count', 'updated_at'])

        if participant.paid_count >= participant.required_paid_referrals:
            _grant_win(participant)
            return participant

        now = datetime.now()
        if block_on_expire and now >= participant.deadline_at:
            _block_participant(
                participant,
                reason=(
                    f'Required {participant.required_paid_referrals} paid referrals '
                    f'within {participant.window_hours} hours were not completed.'
                ),
            )
            return participant

        return participant


def evaluate_agent(agent, *, block_on_expire=True):
    participant = get_participant_for_agent(agent)
    if not participant:
        return None
    return evaluate_participant(participant, block_on_expire=block_on_expire)


def admin_grant_win(participant):
    """Manual grant from admin."""
    with transaction.atomic():
        participant = EventReferralParticipant.objects.select_for_update().get(pk=participant.pk)
        if participant.status != EventReferralParticipant.STATUS_WON:
            _grant_win(participant)
    participant.refresh_from_db()
    return participant


def admin_restore_participant(participant, *, extend_hours=0):
    with transaction.atomic():
        participant = EventReferralParticipant.objects.select_for_update().get(pk=participant.pk)
        agent = Agent.objects.select_for_update().get(pk=participant.agent_id)
        if extend_hours:
            from datetime import timedelta
            participant.deadline_at = participant.deadline_at + timedelta(hours=int(extend_hours))
        if participant.status == EventReferralParticipant.STATUS_WON:
            # Re-activating a winner made the next evaluation grant the win
            # again and push an approved agent back to pending_approval.
            participant.save(update_fields=['deadline_at', 'updated_at'])
            participant.refresh_from_db()
            return participant
        participant.status = EventReferralParticipant.STATUS_ACTIVE
        participant.blocked_at = None
        participant.blocked_reason = ''
        participant.save()
        if agent.status in ('suspended', 'pending_payment', 'event_challenge'):
            agent.status = 'event_challenge' if not agent.plan_type else 'pending_approval'
            agent.save(update_fields=['status', 'updated_at'])
    participant.refresh_from_db()
    return participant
