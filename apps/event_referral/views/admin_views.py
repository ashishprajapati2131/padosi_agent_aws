import logging

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.admin_panel.auth import _get_admin_from_session
from apps.event_referral.models import EventReferralCampaign, EventReferralParticipant
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

    from datetime import datetime
    from apps.event_referral.services.participant_service import expire_admin_grant_if_due

    now = datetime.now()
    refreshed = []
    for participant in participants:
        if (
            participant.grant_plan_slug
            and participant.grant_expires_at
            and participant.grant_expires_at <= now
        ):
            participant = expire_admin_grant_if_due(participant)
        refreshed.append(participant)
    participants = refreshed

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
    from datetime import datetime, timedelta

    from apps.event_referral.services.participant_service import _normalize_grant_plan

    participant = get_object_or_404(EventReferralParticipant, pk=participant_id)
    raw_plan = (request.POST.get('plan') or 'basic').strip().lower()
    plan = _normalize_grant_plan(raw_plan)
    if not plan:
        messages.error(request, 'Choose Basic or Professional.')
        return redirect('admin_event_referral_dashboard')

    duration = (request.POST.get('duration') or 'permanent').strip().lower()
    expires_at = None
    days = None
    if duration == 'temporary':
        try:
            days = int(request.POST.get('grant_days') or 30)
        except (TypeError, ValueError):
            days = 0
        if days < 1 or days > 365:
            messages.error(request, 'A temporary grant must be between 1 and 365 days.')
            return redirect('admin_event_referral_dashboard')
        expires_at = datetime.now() + timedelta(days=days)
    elif duration != 'permanent':
        messages.error(request, 'Choose a permanent grant or a temporary one.')
        return redirect('admin_event_referral_dashboard')

    admin_grant_win(participant, plan_slug=plan, expires_at=expires_at)
    label = 'Professional' if plan == 'professional' else 'Basic'
    if days:
        messages.success(request, f'{label} plan granted for {days} days.')
    else:
        messages.success(request, f'{label} plan granted permanently.')
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


def admin_trial_activity_logs(request):
    """
    Trial Agent Activity Tracking & Audit Logs dashboard.
    Tracks all activity of Free Trial / Paldi festive grant agents:
    - Logins
    - Dashboard visits
    - Profile edits
    - Public profile views & visiting card views
    - Upgrade modal clicks & checkouts
    - Plan upgrade conversions (paid)
    """
    if not _require_admin(request):
        return redirect('/admin/login/')

    from django.db.models import Q, Count, Max
    from django.utils import timezone
    from datetime import timedelta
    import csv
    from django.http import HttpResponse
    from django.core.paginator import Paginator
    from apps.event_referral.models import TrialAgentActivityLog, EventReferralParticipant
    from apps.agents.models import Agent, AgentSubscription

    # 1. Base query for activity logs
    logs_qs = TrialAgentActivityLog.objects.select_related('agent', 'participant').order_by('-created_at')

    search_query = (request.GET.get('q') or '').strip()
    activity_type = (request.GET.get('activity_type') or '').strip()
    date_filter = (request.GET.get('date_range') or 'all').strip()
    selected_agent_id = (request.GET.get('agent_id') or '').strip()

    if selected_agent_id and selected_agent_id.isdigit():
        logs_qs = logs_qs.filter(agent_id=int(selected_agent_id))

    if search_query:
        logs_qs = logs_qs.filter(
            Q(agent__fullname__icontains=search_query)
            | Q(agent__email__icontains=search_query)
            | Q(agent__mobile__icontains=search_query)
            | Q(participant__referral_code__icontains=search_query)
            | Q(title__icontains=search_query)
            | Q(description__icontains=search_query)
        )

    if activity_type:
        logs_qs = logs_qs.filter(activity_type=activity_type)

    now = timezone.now()
    if date_filter == 'today':
        logs_qs = logs_qs.filter(created_at__date=now.date())
    elif date_filter == '7d':
        logs_qs = logs_qs.filter(created_at__gte=now - timedelta(days=7))
    elif date_filter == '30d':
        logs_qs = logs_qs.filter(created_at__gte=now - timedelta(days=30))

    # CSV Export
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="trial_agent_activity_logs_{now.strftime("%Y%m%d_%H%M")}.csv"'
        from apps.admin_panel.services.spreadsheet_safety import safe_csv_writer
        writer = safe_csv_writer(response)
        writer.writerow(['ID', 'Timestamp', 'Agent ID', 'Agent Name', 'Mobile', 'Email', 'Activity Type', 'Title', 'Description', 'IP Address', 'User Agent'])
        for item in logs_qs[:5000].iterator():
            writer.writerow([
                item.id,
                item.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                item.agent_id,
                getattr(item.agent, 'fullname', '') or '',
                getattr(item.agent, 'mobile', '') or '',
                getattr(item.agent, 'email', '') or '',
                item.activity_type,
                item.title,
                item.description,
                item.ip_address,
                item.user_agent,
            ])
        return response

    # 2. KPI Metrics
    trial_participants_qs = EventReferralParticipant.objects.select_related('agent').filter(
        Q(grant_expires_at__isnull=False) | Q(agent__status__in=['event_challenge', 'trial']) | Q(agent__plan_type='free_trial')
    )
    total_trial_agents = trial_participants_qs.count()
    trial_agent_ids_all = set(trial_participants_qs.values_list('agent_id', flat=True))

    logged_in_agent_ids = set(TrialAgentActivityLog.objects.filter(activity_type='login').values_list('agent_id', flat=True))
    profile_edited_agent_ids = set(TrialAgentActivityLog.objects.filter(activity_type='profile_edit').values_list('agent_id', flat=True))
    upgrade_initiated_agent_ids = set(TrialAgentActivityLog.objects.filter(activity_type__in=['upgrade_modal_open', 'upgrade_initiated']).values_list('agent_id', flat=True))
    upgrade_paid_agent_ids = set(TrialAgentActivityLog.objects.filter(activity_type='upgrade_success').values_list('agent_id', flat=True))

    paid_subs_agent_ids = set(AgentSubscription.objects.filter(
        payment_status='completed'
    ).exclude(
        razorpay_payment_id__isnull=True, razorpay_order_id__isnull=True
    ).values_list('agent_id', flat=True))

    all_upgraded_trial_agent_ids = (upgrade_paid_agent_ids | (paid_subs_agent_ids & trial_agent_ids_all))

    total_profile_views = TrialAgentActivityLog.objects.filter(activity_type__in=['profile_view', 'card_view']).count()

    conversion_rate = 0.0
    if total_trial_agents > 0:
        conversion_rate = round((len(all_upgraded_trial_agent_ids) / total_trial_agents) * 100, 1)

    kpi_stats = {
        'total_trial_agents': total_trial_agents,
        'total_logged_in': len(logged_in_agent_ids & trial_agent_ids_all) if trial_agent_ids_all else len(logged_in_agent_ids),
        'total_profile_edited': len(profile_edited_agent_ids & trial_agent_ids_all) if trial_agent_ids_all else len(profile_edited_agent_ids),
        'total_profile_views': total_profile_views,
        'total_upgrade_clicks': len(upgrade_initiated_agent_ids & trial_agent_ids_all) if trial_agent_ids_all else len(upgrade_initiated_agent_ids),
        'total_upgraded_paid': len(all_upgraded_trial_agent_ids),
        'conversion_rate': conversion_rate,
    }

    # 3. Agent Roster Breakdown
    roster_search = (request.GET.get('roster_q') or '').strip()
    roster_qs = trial_participants_qs
    if roster_search:
        roster_qs = roster_qs.filter(
            Q(agent__fullname__icontains=roster_search)
            | Q(agent__mobile__icontains=roster_search)
            | Q(agent__email__icontains=roster_search)
            | Q(referral_code__icontains=roster_search)
        )

    log_counts = (
        TrialAgentActivityLog.objects
        .values('agent_id', 'activity_type')
        .annotate(total=Count('id'))
    )
    agent_activity_counts = {}
    for row in log_counts:
        aid = row['agent_id']
        atype = row['activity_type']
        if aid not in agent_activity_counts:
            agent_activity_counts[aid] = {'login': 0, 'profile_edit': 0, 'profile_view': 0, 'card_view': 0, 'upgrade_initiated': 0, 'upgrade_modal_open': 0, 'upgrade_success': 0}
        agent_activity_counts[aid][atype] = row['total']

    latest_logins = dict(
        TrialAgentActivityLog.objects.filter(activity_type='login')
        .values('agent_id')
        .annotate(latest=Max('created_at'))
        .values_list('agent_id', 'latest')
    )

    roster_items = []
    for p in roster_qs[:500]:
        agent = p.agent
        counts = agent_activity_counts.get(agent.id, {})
        has_paid_upgrade = agent.id in all_upgraded_trial_agent_ids
        roster_items.append({
            'participant': p,
            'agent': agent,
            'logins_count': counts.get('login', 0),
            'last_login': latest_logins.get(agent.id),
            'profile_edits_count': counts.get('profile_edit', 0),
            'profile_views_count': counts.get('profile_view', 0) + counts.get('card_view', 0),
            'upgrade_initiated_count': counts.get('upgrade_initiated', 0) + counts.get('upgrade_modal_open', 0),
            'is_upgraded': has_paid_upgrade,
            'plan_type': agent.plan_type,
            'status': agent.status,
            'grant_expires_at': p.grant_expires_at,
        })

    # 4. Pagination
    total_logs_count = logs_qs.count()
    paginator = Paginator(logs_qs, 50)
    page_number = request.GET.get('page') or 1
    page_obj = paginator.get_page(page_number)

    selected_agent = None
    if selected_agent_id and selected_agent_id.isdigit():
        selected_agent = Agent.objects.filter(pk=int(selected_agent_id)).first()

    context = {
        'kpi': kpi_stats,
        'page_obj': page_obj,
        'roster_items': roster_items,
        'search_query': search_query,
        'activity_type': activity_type,
        'date_filter': date_filter,
        'selected_agent': selected_agent,
        'selected_agent_id': selected_agent_id,
        'roster_search': roster_search,
        'activity_choices': TrialAgentActivityLog.ACTIVITY_CHOICES,
        'total_logs_count': total_logs_count,
    }
    return render(request, 'event_referral/admin/trial_activity_logs.html', context)

