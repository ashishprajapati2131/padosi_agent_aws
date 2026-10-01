import json
import logging

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.event_referral.models import EventReferral, EventReferralCampaign, EventReferralParticipant
from apps.event_referral.services.participant_service import (
    _block_participant,
    admin_grant_win,
    # Aliased: the view below has the same name and used to shadow it, so
    # Extend / Restore always failed with a TypeError.
    admin_restore_participant as restore_participant_service,
)

logger = logging.getLogger(__name__)


def _require_admin(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return None
    return admin


def admin_dashboard(request):
    if not _require_admin(request):
        return redirect('/admin/login/')

    from apps.event_referral.services.db_utils import run_with_db_retry
    from apps.event_referral.services.schema_compat import ensure_event_referral_metrics_schema

    if not ensure_event_referral_metrics_schema():
        messages.error(
            request,
            'Event referral database schema is still updating. Please refresh in a few seconds.',
        )

    def _load_dashboard_context():
        campaign = EventReferralCampaign.get_current()
        participants = (
            EventReferralParticipant.objects.select_related('agent')
            .order_by('-registered_at')[:200]
        )
        stats = {
            'total': EventReferralParticipant.objects.count(),
            'active': EventReferralParticipant.objects.filter(status='active').count(),
            'won': EventReferralParticipant.objects.filter(status='won').count(),
            'blocked': EventReferralParticipant.objects.filter(status='blocked').count(),
        }
        campaign.refresh_from_db(fields=['registration_link_open_count'])
        return campaign, participants, stats

    campaign, participants, stats = run_with_db_retry(_load_dashboard_context)

    from django.conf import settings

    public_base = (getattr(settings, 'APP_URL', '') or '').rstrip('/')
    if not public_base:
        public_base = request.build_absolute_uri('/').rstrip('/')

    return render(
        request,
        'event_referral/admin/dashboard.html',
        {
            'campaign': campaign,
            'participants': participants,
            'stats': stats,
            'show_test_tools': _test_tools_allowed(),
            'event_registration_public_url': f'{public_base}/event-registration/',
        },
    )


@require_POST
def admin_toggle_registration(request):
    if not _require_admin(request):
        return redirect('/admin/login/')

    campaign = EventReferralCampaign.get_current()
    campaign.is_enabled = not campaign.is_enabled
    campaign.save(update_fields=['is_enabled', 'updated_at'])
    if campaign.is_enabled:
        messages.success(request, 'Event registration page is now LIVE.')
    else:
        messages.warning(request, 'Event registration page is now OFF (visitors see closed message).')
    return redirect('admin_event_referral_dashboard')


@require_POST
def admin_update_settings(request):
    if not _require_admin(request):
        return redirect('/admin/login/')

    campaign = EventReferralCampaign.get_current()
    campaign.is_enabled = request.POST.get('is_enabled') == 'on'
    try:
        campaign.window_hours = max(1, int(request.POST.get('window_hours', campaign.window_hours)))
        campaign.required_paid_referrals = max(
            1, int(request.POST.get('required_paid_referrals', campaign.required_paid_referrals)),
        )
    except (TypeError, ValueError):
        messages.error(request, 'Invalid numeric settings.')
        return redirect('admin_event_referral_dashboard')

    campaign.reward_plan_slug = (request.POST.get('reward_plan_slug') or 'basic').strip()
    campaign.page_title = (request.POST.get('page_title') or campaign.page_title).strip()
    campaign.page_instructions = (request.POST.get('page_instructions') or '').strip()
    campaign.save()
    messages.success(request, 'Event referral settings saved.')
    return redirect('admin_event_referral_dashboard')


@require_POST
def admin_extend_deadline(request, participant_id):
    if not _require_admin(request):
        return redirect('/admin/login/')
    participant = get_object_or_404(EventReferralParticipant, pk=participant_id)
    try:
        hours = int(request.POST.get('extend_hours', 0))
    except (TypeError, ValueError):
        hours = 0
    if hours > 0:
        restore_participant_service(participant, extend_hours=hours)
        messages.success(request, f'Extended deadline by {hours} hours.')
    return redirect('admin_event_referral_dashboard')


@require_POST
def admin_update_target(request, participant_id):
    if not _require_admin(request):
        return redirect('/admin/login/')
    participant = get_object_or_404(EventReferralParticipant, pk=participant_id)
    try:
        target = max(1, int(request.POST.get('required_paid_referrals', participant.required_paid_referrals)))
    except (TypeError, ValueError):
        messages.error(request, 'Invalid target.')
        return redirect('admin_event_referral_dashboard')
    participant.required_paid_referrals = target
    participant.save(update_fields=['required_paid_referrals', 'updated_at'])
    messages.success(request, 'Referral target updated for this participant.')
    return redirect('admin_event_referral_dashboard')


@require_POST
def admin_grant_plan(request, participant_id):
    if not _require_admin(request):
        return redirect('/admin/login/')
    participant = get_object_or_404(EventReferralParticipant, pk=participant_id)
    admin_grant_win(participant)
    messages.success(request, 'Basic plan granted.')
    return redirect('admin_event_referral_dashboard')


@require_POST
def admin_block_participant(request, participant_id):
    if not _require_admin(request):
        return redirect('/admin/login/')
    participant = get_object_or_404(EventReferralParticipant, pk=participant_id)
    reason = (request.POST.get('reason') or 'Blocked by admin.').strip()
    _block_participant(participant, reason=reason, by_admin=True)
    messages.success(request, 'Participant blocked. Their login is disabled.')
    return redirect('admin_event_referral_dashboard')


@require_POST
def admin_restore_participant(request, participant_id):
    if not _require_admin(request):
        return redirect('/admin/login/')
    participant = get_object_or_404(EventReferralParticipant, pk=participant_id)
    try:
        hours = int(request.POST.get('extend_hours', 0))
    except (TypeError, ValueError):
        hours = 0
    participant = restore_participant_service(participant, extend_hours=hours)
    outcome = getattr(participant, 'restore_outcome', '')
    if outcome == 'kept_earned_win':
        messages.warning(request, 'This participant earned the win with paid referrals, so it was kept.')
    elif outcome == 'undid_grant':
        messages.success(request, 'Granted plan removed; the participant is back in the challenge.')
    else:
        messages.success(request, 'Participant restored.')
    from datetime import datetime
    if participant.status == EventReferralParticipant.STATUS_ACTIVE and participant.deadline_at <= datetime.now():
        messages.warning(request, 'Their deadline has already passed; use Extend to give them more time.')
    return redirect('admin_event_referral_dashboard')


# -- Local testing only (DEBUG) ------------------------------------------------
# Adds fake *paid* referrals through the real counting path, so the 48-hour
# challenge can be tested without real payments. Never available on the live
# site: a staff member could otherwise hand out free plans.
TEST_REFERRAL_EMAIL_DOMAIN = 'paldi-test.invalid'


def _test_tools_allowed():
    from django.conf import settings
    return bool(settings.DEBUG)


@require_POST
def admin_test_add_referrals(request, participant_id):
    from django.http import Http404
    if not _test_tools_allowed():
        raise Http404()
    if not _require_admin(request):
        return redirect('/admin/login/')
    import random
    import uuid
    from apps.agents.models import Agent, AgentSubscription
    from apps.event_referral.services.qualification_service import qualify_event_referral, register_referred_agent

    participant = get_object_or_404(EventReferralParticipant.objects.select_related('agent'), pk=participant_id)
    try:
        count = max(1, min(10, int(request.POST.get('count', 1))))
    except (TypeError, ValueError):
        count = 1
    referrer_mobile = ''.join(c for c in str(participant.agent.mobile or '') if c.isdigit())[-10:]
    added = 0
    for _ in range(count):
        token = uuid.uuid4().hex[:10]
        mobile = ''
        for _attempt in range(20):
            candidate = '7' + ''.join(random.choice('0123456789') for _d in range(9))
            if candidate != referrer_mobile and not Agent.objects.filter(mobile=candidate).exists():
                mobile = candidate
                break
        if not mobile:
            continue
        friend = Agent.objects.create(
            fullname=f'TEST Referral {token[:4].upper()}',
            email=f'test.{participant.referral_code.lower()}.{token}@{TEST_REFERRAL_EMAIL_DOMAIN}',
            mobile=mobile, status='active', plan_type='starter',
            referred_by_code=participant.referral_code,
        )
        register_referred_agent(friend)
        subscription = AgentSubscription.objects.create(
            agent=friend, selected_plan="Starter's Plan", registration_amount='0.00',
            payment_status='completed', status='active',
            razorpay_order_id=f'order_TESTREF{token}', razorpay_payment_id=f'pay_TESTREF{token}',
        )
        qualify_event_referral(friend, subscription)
        added += 1
    participant.refresh_from_db()
    messages.success(request, f'TEST: added {added} paid referral(s). Progress {participant.paid_count} / '
                              f'{participant.required_paid_referrals}, status {participant.status}.')
    return redirect('admin_event_referral_dashboard')


@require_POST
def admin_test_remove_referrals(request, participant_id):
    from django.http import Http404
    if not _test_tools_allowed():
        raise Http404()
    if not _require_admin(request):
        return redirect('/admin/login/')
    from apps.agents.models import Agent
    from apps.event_referral.services.participant_service import _recount_paid

    participant = get_object_or_404(EventReferralParticipant, pk=participant_id)
    fakes = list(Agent.objects.filter(referred_by_code=participant.referral_code,
                                      email__iendswith='@' + TEST_REFERRAL_EMAIL_DOMAIN))
    EventReferral.objects.filter(participant=participant, referred_agent__in=fakes).delete()
    from django.db import transaction
    for agent in fakes:
        try:
            with transaction.atomic():
                agent.delete()
        except Exception:
            # A legacy table can block the cascade; detach the fake instead.
            Agent.objects.filter(pk=agent.pk).update(status='deleted', referred_by_code='')
            agent.subscriptions.filter(razorpay_order_id__startswith='order_TESTREF').delete()
    participant.paid_count = _recount_paid(participant)
    participant.save(update_fields=['paid_count', 'updated_at'])
    messages.success(request, f'TEST: removed {len(fakes)} test referral(s). Progress {participant.paid_count} / '
                              f'{participant.required_paid_referrals}. A test win stays until you press Restore.')
    return redirect('admin_event_referral_dashboard')
