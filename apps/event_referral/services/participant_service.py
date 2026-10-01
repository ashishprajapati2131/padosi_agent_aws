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
    if participant.status == EventReferralParticipant.STATUS_BLOCKED and participant.blocked_by_admin:
        # Blocked by an admin: no Paldi dashboard (and login stays suspended).
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
    # Never take anything away: an already-approved agent stays active, and an
    # agent who meanwhile paid for an equal or higher plan keeps it (the win
    # used to push them back to pending approval on the basic plan).
    from plan_upgrade_handoff import plan_rank
    if agent.status != 'active':
        agent.status = 'pending_approval'
    if plan_rank(plan) >= plan_rank(agent.plan_type or ''):
        agent.plan_type = plan
    agent.registration_step = max(agent.registration_step or 1, 2)
    agent.save(update_fields=['status', 'plan_type', 'registration_step', 'updated_at'])
    logger.info(
        'Event referral win: agent #%s participant %s plan=%s',
        agent.id,
        participant.referral_code,
        plan,
    )


def _block_participant(participant, reason='', by_admin=False):
    """Block a challenger. Deadline blocks keep a locked dashboard and let
    them buy a plan; an admin block (by_admin) also suspends the login of an
    agent who has not paid or been approved."""
    participant.status = EventReferralParticipant.STATUS_BLOCKED
    participant.blocked_at = datetime.now()
    participant.blocked_reason = reason or 'Deadline passed without enough paid referrals.'
    participant.blocked_by_admin = bool(by_admin)
    participant.save(
        update_fields=['status', 'blocked_at', 'blocked_reason', 'blocked_by_admin', 'updated_at'],
    )
    agent = participant.agent
    if agent.status not in ('active', 'pending_approval'):
        agent.status = 'suspended' if by_admin else 'pending_payment'
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
            if _recount_paid(participant) >= participant.required_paid_referrals:
                # Earned with real paid referrals: Restore never takes it away
                # (re-activating made the next evaluation grant it again).
                participant.save(update_fields=['deadline_at', 'updated_at'])
                participant.refresh_from_db()
                participant.restore_outcome = 'kept_earned_win'
                return participant
            # An admin "Grant plan": Restore undoes it, so the agent leaves
            # the Approvals queue and is back in the challenge. An agent who
            # paid for a plan themselves keeps their plan and status.
            participant.status = EventReferralParticipant.STATUS_ACTIVE
            participant.won_at = None
            participant.blocked_at = None
            participant.blocked_reason = ''
            participant.save()
            from apps.agents.services.account_auth import agent_has_completed_payment
            if not agent_has_completed_payment(agent):
                fields = ['status', 'updated_at']
                agent.status = 'event_challenge'
                if agent.plan_type == (participant.reward_plan_slug or 'basic'):
                    agent.plan_type = ''
                    fields.append('plan_type')
                agent.save(update_fields=fields)
            participant.refresh_from_db()
            participant.restore_outcome = 'undid_grant'
            return participant
        participant.status = EventReferralParticipant.STATUS_ACTIVE
        participant.blocked_at = None
        participant.blocked_reason = ''
        participant.blocked_by_admin = False
        participant.save()
        if agent.status in ('suspended', 'pending_payment', 'event_challenge'):
            agent.status = 'event_challenge' if not agent.plan_type else 'pending_approval'
            agent.save(update_fields=['status', 'updated_at'])
    participant.refresh_from_db()
    return participant


def _has_real_payment_records(agent):
    """Completed/refunded real payments or invoices (kept for GST / the CA)."""
    from apps.agents.models import AgentSubscription, Invoice
    from apps.agents.services.test_markers import TEST_ORDER_PREFIX, TEST_PAYMENT_PREFIX
    real_subs = (AgentSubscription.objects.filter(agent=agent, payment_status__in=['completed', 'refunded'])
                 .exclude(razorpay_payment_id__startswith=TEST_PAYMENT_PREFIX)
                 .exclude(razorpay_order_id__startswith=TEST_ORDER_PREFIX))
    return real_subs.exists() or Invoice.objects.filter(agent_id=agent.pk).exists()


def remove_test_referrals(participant):
    """Delete the testing-mode fake referrals of a participant and take them
    out of the Paldi and championship counts. Returns how many were removed."""
    from apps.agents.services.test_markers import TEST_EMAIL_DOMAIN
    from apps.referral_championship.services.qualification_service import revert_championship_qualification

    fakes = list(Agent.objects.filter(referred_by_code=participant.referral_code,
                                      email__iendswith='@' + TEST_EMAIL_DOMAIN))
    EventReferral.objects.filter(participant=participant, referred_agent__in=fakes).delete()
    for fake in fakes:
        try:
            revert_championship_qualification(fake, reason='test removed')
        except Exception:
            logger.exception('Championship revert failed for test referral %s', fake.pk)
        try:
            with transaction.atomic():
                fake.delete()
        except Exception:
            # A legacy table can block the cascade; detach the fake instead.
            Agent.objects.filter(pk=fake.pk).update(status='deleted', referred_by_code='')
            fake.subscriptions.filter(razorpay_order_id__startswith='order_TESTREF').delete()
    participant.paid_count = _recount_paid(participant)
    participant.save(update_fields=['paid_count', 'updated_at'])
    try:
        from apps.referral_championship.models import ChampionshipParticipant, ChampionshipRewardClaim
        for cp in ChampionshipParticipant.objects.filter(agent_id=participant.agent_id):
            ChampionshipRewardClaim.objects.filter(
                participant=cp, status__in=['locked', 'unlocked'],
                reward_slab__threshold__gt=cp.qualifying_referrals_count,
            ).delete()
    except Exception:
        logger.exception('Could not withdraw test-unlocked claims for participant %s', participant.pk)
    return len(fakes)


def admin_delete_participant(participant):
    """Remove a Paldi challenger (e.g. a test signup) and its event data.

    The agent account itself is deleted only when it has no real payment or
    invoice; otherwise it is kept for GST records and only the event data
    goes. Staff / insurance / distributor logins are never deleted.
    Returns 'agent_deleted' or 'event_data_removed'.
    """
    from django.contrib.auth.models import User
    from django.db import connection
    from apps.agents.models import AgentDraft
    from apps.agents.services.account_auth import is_non_agent_portal_user

    agent = participant.agent
    remove_test_referrals(participant)
    keep_agent = _has_real_payment_records(agent)

    with transaction.atomic():
        EventReferral.objects.filter(participant=participant).delete()
        participant.delete()
        try:
            from apps.referral_championship.models import ChampionshipParticipant
            ChampionshipParticipant.objects.filter(agent=agent).delete()
        except Exception:
            logger.exception('Championship participant cleanup failed for agent %s', agent.pk)

    if keep_agent:
        logger.warning('Paldi participant removed; agent #%s kept (payment records)', agent.pk)
        return 'event_data_removed'

    email = (agent.email or '').strip()
    user = agent.user if agent.user_id else None
    agent_pk = agent.pk
    try:
        with transaction.atomic():
            agent.delete()
    except Exception:
        # A legacy table can block the cascade: hide the account instead.
        logger.exception('Hard delete of agent #%s failed; marking it deleted', agent_pk)
        Agent.objects.filter(pk=agent_pk).update(status='deleted', referred_by_code='')
    with transaction.atomic():
        if email:
            AgentDraft.objects.filter(email__iexact=email).delete()
        if user and not is_non_agent_portal_user(user):
            if Agent.objects.filter(pk=agent_pk).exists():
                User.objects.filter(pk=user.pk).update(is_active=False)
            else:
                User.objects.filter(pk=user.pk).delete()
        if email:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM users WHERE LOWER(email) = LOWER(%s) AND LOWER(COALESCE(role, '')) IN ('agent', 'client', 'user', '')",
                    [email],
                )
    logger.warning('Paldi participant and agent #%s deleted by admin', agent_pk)
    return 'agent_deleted'
