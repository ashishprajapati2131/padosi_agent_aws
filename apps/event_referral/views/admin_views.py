import json
import logging

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
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
            'show_test_tools': _test_tools_allowed(request),
            'is_super_admin': _is_super_admin(request),
            'test_mode_until': _test_mode_until(),
            'debug_mode': settings.DEBUG,
            'event_registration_public_url': f"{public_base}{reverse('event_referral:register')}",
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


# -- Testing mode ---------------------------------------------------------------
# Adds fake *paid* referrals through the real counting path, so the 48-hour
# challenge and championship can be tested without real payments. Razorpay is
# never called and test subscriptions never get an invoice (no invoice number
# is used; see apps/agents/services/test_markers.py). Always on locally
# (DEBUG); on the live site only a Super Admin can switch it on, and it turns
# itself off after TEST_MODE_HOURS.
from apps.agents.services.test_markers import (  # noqa: E402
    TEST_EMAIL_DOMAIN as TEST_REFERRAL_EMAIL_DOMAIN,
    TEST_ORDER_PREFIX,
    TEST_PAYMENT_PREFIX,
)

TEST_MODE_SETTING = 'event_test_tools_until'
TEST_MODE_HOURS = 2


def _is_super_admin(request):
    return getattr(getattr(request, 'admin_user', None), 'role', '') == 'super'


def _test_mode_until():
    import time
    from apps.home.models import SiteSetting
    try:
        until = float(SiteSetting.get_value(TEST_MODE_SETTING, 0) or 0)
    except (TypeError, ValueError):
        until = 0
    return until if until > time.time() else 0


def _test_tools_allowed(request=None):
    from django.conf import settings
    if settings.DEBUG:
        return True
    return bool(request is not None and _is_super_admin(request) and _test_mode_until())


@require_POST
def admin_toggle_test_mode(request):
    import time
    from django.http import Http404
    from apps.home.models import SiteSetting
    if not _require_admin(request):
        return redirect('/admin/login/')
    if not _is_super_admin(request):
        raise Http404()
    if request.POST.get('enable') == '1':
        SiteSetting.set_value(TEST_MODE_SETTING, str(int(time.time() + TEST_MODE_HOURS * 3600)), 'event')
        logger.warning('Event referral testing mode switched ON for %s hours', TEST_MODE_HOURS)
        messages.warning(request, f'Testing mode is ON for {TEST_MODE_HOURS} hours. Remove test referrals when done.')
    else:
        SiteSetting.set_value(TEST_MODE_SETTING, '0', 'event')
        logger.warning('Event referral testing mode switched OFF')
        messages.success(request, 'Testing mode is OFF.')
    return redirect('admin_event_referral_dashboard')


@require_POST
def admin_test_add_referrals(request, participant_id):
    from django.http import Http404
    if not _test_tools_allowed(request):
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
            mobile=mobile, status='incomplete', plan_type='starter',
            referred_by_code=participant.referral_code,
        )
        register_referred_agent(friend)
        subscription = AgentSubscription.objects.create(
            agent=friend, selected_plan="Starter's Plan", registration_amount='0.00',
            payment_status='completed', status='active',
            razorpay_order_id=f'{TEST_ORDER_PREFIX}{token}', razorpay_payment_id=f'{TEST_PAYMENT_PREFIX}{token}',
        )
        qualify_event_referral(friend, subscription)
        from apps.referral_championship.services.qualification_service import process_championship_qualification
        process_championship_qualification(friend, subscription)
        added += 1
    participant.refresh_from_db()
    messages.success(request, f'TEST: added {added} paid referral(s). Progress {participant.paid_count} / '
                              f'{participant.required_paid_referrals}, status {participant.status}.')
    return redirect('admin_event_referral_dashboard')


@require_POST
def admin_test_remove_referrals(request, participant_id):
    from django.http import Http404
    if not _test_tools_allowed(request):
        raise Http404()
    if not _require_admin(request):
        return redirect('/admin/login/')
    from apps.event_referral.services.participant_service import remove_test_referrals

    participant = get_object_or_404(EventReferralParticipant, pk=participant_id)
    removed = remove_test_referrals(participant)
    participant.refresh_from_db()
    messages.success(request, f'TEST: removed {removed} test referral(s). Progress {participant.paid_count} / '
                              f'{participant.required_paid_referrals}. A test win stays until you press Restore.')
    return redirect('admin_event_referral_dashboard')


@require_POST
def admin_delete_participant(request, participant_id):
    """Super Admin: delete a challenger (e.g. a test signup) and its event data."""
    from django.http import Http404
    from apps.event_referral.services.participant_service import admin_delete_participant as delete_service
    if not _require_admin(request):
        return redirect('/admin/login/')
    if not (settings.DEBUG or _is_super_admin(request)):
        raise Http404()
    participant = get_object_or_404(EventReferralParticipant.objects.select_related('agent'), pk=participant_id)
    label = f'{participant.agent.fullname} ({participant.agent.email})'
    outcome = delete_service(participant)
    if outcome == 'agent_deleted':
        messages.success(request, f'Deleted {label} and all its event data.')
    else:
        messages.warning(request, f'Removed {label} from the event. The agent has real payment or invoice '
                                  f'records, so the account was kept (manage it under Agents).')
    return redirect('admin_event_referral_dashboard')
