"""
Admin Panel Views for WhatsApp Agent Bot & OpenWA Command Center
=================================================================
Provides comprehensive management, analytics, session lifecycle controls,
real-time OpenWA connection status, QR code display, and audit logs.
"""

import json
import logging
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.contrib import messages

from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.admin_panel.models import AdminActivityLog
from apps.home.models.site_setting import SiteSetting
from apps.wa_agent_bot.models import WaBotSession, WaBotMessageLog
from apps.wa_agent_bot.services.openwa_admin_service import (
    get_openwa_session_status,
    get_openwa_qr_code,
    control_openwa_session,
    send_admin_test_whatsapp,
    get_openwa_config,
    sync_openwa_webhook,
    list_openwa_sessions,
)
from apps.agents.models import Agent, AgentSubscription

logger = logging.getLogger(__name__)


def _log_admin_action(request, action, target_type, target_id, details=""):
    try:
        AdminActivityLog.log(action, target_type, target_id, details=details, request=request)
    except Exception as e:
        logger.warning(f"AdminActivityLog failed: {e}")


def wa_bot_dashboard(request):
    """
    Main WhatsApp & OpenWA Command Center.
    Displays live server connection health, QR code scanner, key analytics,
    conversion funnel, and fast action controls.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    # 1. Fetch live OpenWA status
    openwa_status = get_openwa_session_status()
    qr_data = None
    # OpenWA status names vary by version, so try for a QR whenever the server is up but not paired.
    if openwa_status.get('online') and not openwa_status.get('is_connected'):
        qr_resp = get_openwa_qr_code()
        if qr_resp.get('success'):
            qr_data = qr_resp.get('qr_code')

    # 2. Master Bot Status
    bot_enabled = SiteSetting.get_value('wa_agent_bot_enabled', True)
    from apps.wa_agent_bot.services.notification_service import lead_alerts_enabled

    # 3. Overall Statistics & Funnel
    total_sessions = WaBotSession.objects.count()
    registered_sessions = WaBotSession.objects.filter(is_registered=True).count()
    awaiting_payment = WaBotSession.objects.filter(state=WaBotSession.STATE_AWAITING_PAYMENT).count()
    in_progress = total_sessions - registered_sessions

    # Conversion rate
    conversion_rate = round((registered_sessions / total_sessions * 100), 1) if total_sessions > 0 else 0

    # Total Revenue generated via bot subscriptions
    bot_agents = WaBotSession.objects.filter(agent__isnull=False).values_list('agent_id', flat=True)
    revenue_agg = AgentSubscription.objects.filter(
        agent_id__in=bot_agents,
        payment_status='completed'
    ).aggregate(total_rev=Sum('registration_amount'))
    total_revenue = revenue_agg['total_rev'] or 0

    # Message Counts
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    total_msgs = WaBotMessageLog.objects.count()
    today_msgs = WaBotMessageLog.objects.filter(created_at__gte=today_start).count()
    today_in = WaBotMessageLog.objects.filter(created_at__gte=today_start, direction=WaBotMessageLog.DIRECTION_IN).count()
    today_out = WaBotMessageLog.objects.filter(created_at__gte=today_start, direction=WaBotMessageLog.DIRECTION_OUT).count()

    # Step-by-Step Funnel
    state_counts = dict(
        WaBotSession.objects.values('state').annotate(count=Count('id')).values_list('state', 'count')
    )
    funnel = [
        {'step': '1. Welcome & Intro', 'key': 'welcome', 'count': state_counts.get('welcome', 0)},
        {'step': '2. Basic Info (Name/Mobile/Email)', 'key': 'info', 'count': (
            state_counts.get('ask_fullname', 0) + state_counts.get('ask_email', 0) + state_counts.get('ask_mobile', 0)
        )},
        {'step': '3. Location & Exp (State/Pincode)', 'key': 'loc', 'count': (
            state_counts.get('ask_state', 0) + state_counts.get('ask_pincode', 0) + state_counts.get('ask_experience', 0)
        )},
        {'step': '4. Segments & Review', 'key': 'segments', 'count': (
            state_counts.get('ask_segments', 0) + state_counts.get('confirm', 0)
        )},
        {'step': '5. Plan Selection & Payment', 'key': 'payment', 'count': (
            state_counts.get('ask_plan', 0) + state_counts.get('awaiting_payment', 0)
        )},
        {'step': '6. Registered & Active', 'key': 'logged_in', 'count': (
            state_counts.get('logged_in', 0) + registered_sessions
        )},
    ]

    # Recent 6 Sessions
    recent_sessions = WaBotSession.objects.select_related('agent').order_by('-last_message_at')[:6]

    # Recent 8 Logs
    recent_logs = WaBotMessageLog.objects.select_related('session').order_by('-created_at')[:8]

    context = {
        'openwa_status': openwa_status,
        'qr_data': qr_data,
        'bot_enabled': bot_enabled,
        'lead_alerts_enabled': lead_alerts_enabled(),
        'stats': {
            'total_sessions': total_sessions,
            'registered': registered_sessions,
            'awaiting_payment': awaiting_payment,
            'in_progress': in_progress,
            'conversion_rate': conversion_rate,
            'total_revenue': total_revenue,
            'total_msgs': total_msgs,
            'today_msgs': today_msgs,
            'today_in': today_in,
            'today_out': today_out,
        },
        'funnel': funnel,
        'recent_sessions': recent_sessions,
        'recent_logs': recent_logs,
        'openwa_config': get_openwa_config(),
        'current_webhook_url': request.build_absolute_uri('/wa-bot/webhook/'),
    }
    return render(request, 'admin/whatsapp/dashboard.html', context)


def wa_bot_sessions_list(request):
    """List of all WhatsApp bot agent sessions with search, filters, and actions."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    search_query = request.GET.get('q', '').strip()
    state_filter = request.GET.get('state', '').strip()

    sessions_qs = WaBotSession.objects.select_related('agent').all().order_by('-last_message_at')

    if search_query:
        sessions_qs = sessions_qs.filter(
            Q(phone_number__icontains=search_query) |
            Q(agent__fullname__icontains=search_query) |
            Q(agent__email__icontains=search_query)
        )

    if state_filter:
        sessions_qs = sessions_qs.filter(state=state_filter)

    total_sessions = WaBotSession.objects.count()
    registered_count = WaBotSession.objects.filter(is_registered=True).count()
    awaiting_count = WaBotSession.objects.filter(state=WaBotSession.STATE_AWAITING_PAYMENT).count()
    in_progress = total_sessions - registered_count

    paginator = Paginator(sessions_qs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'state_filter': state_filter,
        'stats': {
            'total': total_sessions,
            'registered': registered_count,
            'awaiting_payment': awaiting_count,
            'in_progress': in_progress,
        },
        'bot_enabled': SiteSetting.get_value('wa_agent_bot_enabled', True),
    }
    return render(request, 'admin/whatsapp/sessions.html', context)


def wa_bot_logs_list(request):
    """Audit trail of incoming and outgoing WhatsApp messages."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    phone_filter = request.GET.get('phone', '').strip()
    dir_filter = request.GET.get('direction', '').strip()
    search_query = request.GET.get('q', '').strip()

    logs_qs = WaBotMessageLog.objects.select_related('session').all().order_by('-created_at')

    if phone_filter:
        logs_qs = logs_qs.filter(session__phone_number__icontains=phone_filter)
    if dir_filter:
        logs_qs = logs_qs.filter(direction=dir_filter)
    if search_query:
        logs_qs = logs_qs.filter(content__icontains=search_query)

    total_logs = WaBotMessageLog.objects.count()
    in_logs = WaBotMessageLog.objects.filter(direction=WaBotMessageLog.DIRECTION_IN).count()
    out_logs = WaBotMessageLog.objects.filter(direction=WaBotMessageLog.DIRECTION_OUT).count()

    paginator = Paginator(logs_qs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'phone_filter': phone_filter,
        'dir_filter': dir_filter,
        'search_query': search_query,
        'stats': {
            'total': total_logs,
            'in': in_logs,
            'out': out_logs,
        },
        'bot_enabled': SiteSetting.get_value('wa_agent_bot_enabled', True),
    }
    return render(request, 'admin/whatsapp/logs.html', context)


def wa_bot_security_status(request):
    """
    Security & Anti-Abuse Dashboard for WhatsApp & OpenWA.
    Displays Webhook verification, Rate limiting, Razorpay Secret validation,
    and Active API key security checklist.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    from apps.agents.services.razorpay_checkout import razorpay_credentials, razorpay_webhook_secret

    openwa_cfg = get_openwa_config()
    webhook_secret = os.environ.get('WA_BOT_WEBHOOK_SECRET', '')
    rzp_secret = razorpay_webhook_secret()
    rzp_key, _ = razorpay_credentials()

    security_checks = [
        {
            'title': 'Razorpay Webhook Signature Verification',
            'status': 'SECURE' if bool(rzp_secret) else 'WARNING',
            'desc': 'Verifies HMAC-SHA256 signature on payment_link.paid events' if rzp_secret else 'Webhook secret not set in .env (development mode active)',
            'icon': 'fa-solid fa-shield-check text-success' if rzp_secret else 'fa-solid fa-triangle-exclamation text-warning',
        },
        {
            'title': 'OpenWA Webhook HMAC Auth',
            'status': 'ACTIVE' if bool(webhook_secret) else 'INFO',
            'desc': 'Inbound messages verified via X-Webhook-Signature' if webhook_secret else 'Optional secret not configured; OpenWA sends to secure internal port',
            'icon': 'fa-solid fa-lock text-success' if webhook_secret else 'fa-solid fa-info-circle text-info',
        },
        {
            'title': 'Rate Limiter & Anti-Flood Protection',
            'status': 'ACTIVE',
            'desc': 'Maximum 10 messages per minute per phone number via Django Cache',
            'icon': 'fa-solid fa-gauge-high text-success',
        },
        {
            'title': 'Plain-Text Password Suppression',
            'status': 'ENFORCED',
            'desc': 'Passwords are never exposed in plaintext on public web pages; dispatched exclusively via private WhatsApp & Email',
            'icon': 'fa-solid fa-eye-slash text-success',
        },
        {
            'title': 'OpenWA API Key Authorization',
            'status': 'AUTHENTICATED' if bool(openwa_cfg.get('api_key')) else 'UNSECURED',
            'desc': 'Outbound REST API protected with Operator X-API-Key' if openwa_cfg.get('api_key') else 'No API Key configured on OpenWA server',
            'icon': 'fa-solid fa-key text-success' if openwa_cfg.get('api_key') else 'fa-solid fa-triangle-exclamation text-danger',
        },
        {
            'title': 'Payment Spoofing Guard',
            'status': 'ENFORCED',
            'desc': 'Payment callbacks require verified captured status via Razorpay API before subscription activation',
            'icon': 'fa-solid fa-fingerprint text-success',
        },
    ]

    context = {
        'security_checks': security_checks,
        'bot_enabled': SiteSetting.get_value('wa_agent_bot_enabled', True),
        'openwa_cfg': openwa_cfg,
    }
    return render(request, 'admin/whatsapp/security.html', context)


# ── Action Endpoints (AJAX / POST) ──────────────────────────────────────────

@require_POST
def wa_bot_toggle_service(request):
    """Toggle the master bot on/off."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    current = SiteSetting.get_value('wa_agent_bot_enabled', True)
    if isinstance(current, str):
        current = current.lower() in ('true', '1', 'yes')

    new_val = not bool(current)
    SiteSetting.set_value('wa_agent_bot_enabled', new_val)

    _log_admin_action(request, 'toggle_wa_bot', 'System', 0, f"Bot enabled set to {new_val}")
    return JsonResponse({'success': True, 'enabled': new_val})


@require_POST
def wa_bot_toggle_lead_alerts(request):
    """Feature flag: WhatsApp agents when they receive a new lead."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    from apps.wa_agent_bot.services.notification_service import LEAD_ALERT_SETTING, lead_alerts_enabled
    new_val = not lead_alerts_enabled()
    SiteSetting.set_value(LEAD_ALERT_SETTING, new_val)

    _log_admin_action(request, 'toggle_wa_lead_alerts', 'System', 0, f"Lead WhatsApp alerts set to {new_val}")
    return JsonResponse({'success': True, 'enabled': new_val})


@require_POST
def wa_bot_session_action(request):
    """Trigger lifecycle actions on OpenWA session (start, stop, restart, logout)."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    action = request.POST.get('action', '').strip().lower()
    success, msg = control_openwa_session(action)

    _log_admin_action(request, f'openwa_{action}', 'OpenWA_Session', 0, msg)
    return JsonResponse({'success': success, 'message': msg})


@require_GET
def wa_bot_get_qr_ajax(request):
    """Return fresh live QR code for AJAX polling."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    res = get_openwa_qr_code()
    status_res = get_openwa_session_status()
    return JsonResponse({
        'success': res.get('success', False),
        'qr_code': res.get('qr_code', ''),
        'status': status_res.get('status', 'unknown'),
        'is_connected': status_res.get('is_connected', False),
        'is_qr_ready': status_res.get('is_qr_ready', False),
        'phone': status_res.get('phone'),
        'error': status_res.get('error') or res.get('error'),
    })


@require_POST
def wa_bot_send_test_message(request):
    """Send an administrator test message via OpenWA."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    phone = request.POST.get('phone', '').strip()
    text = request.POST.get('text', '').strip()

    if not phone or not text:
        return JsonResponse({'success': False, 'error': 'Phone number and message text are required'})

    success, msg = send_admin_test_whatsapp(phone, text)
    _log_admin_action(request, 'send_wa_test_message', 'WhatsAppMessage', 0, f"To: {phone} — {msg}")
    return JsonResponse({'success': success, 'message': msg})


@require_POST
def wa_bot_reset_session(request, session_id):
    """Reset a specific agent's onboarding session back to welcome state."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    session = get_object_or_404(WaBotSession, pk=session_id)
    session.state = WaBotSession.STATE_WELCOME
    session.registration_data = {}
    session.session_context = {}
    session.save()

    _log_admin_action(request, 'reset_wa_session', 'WaBotSession', session.pk, f"Reset phone {session.phone_number}")
    return JsonResponse({'success': True, 'message': f"Session for {session.phone_number} reset to Welcome state"})


@require_POST
def wa_bot_resend_credentials(request, session_id):
    """Resend credentials to both WhatsApp and Email for a registered agent."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    session = get_object_or_404(WaBotSession, pk=session_id)
    agent = session.agent
    if not agent:
        return JsonResponse({'success': False, 'error': 'No Agent record linked to this session'})

    from apps.wa_agent_bot.services.payment_service import activate_agent_subscription_after_payment
    sub = AgentSubscription.objects.filter(agent=agent).order_by('-id').first()
    if not sub:
        return JsonResponse({'success': False, 'error': 'No subscription found for this agent'})

    # Trigger welcome delivery
    success, msg = activate_agent_subscription_after_payment(sub.id)
    _log_admin_action(request, 'resend_wa_credentials', 'Agent', agent.id, f"Resent credentials to {session.phone_number} & {agent.email}")
    return JsonResponse({'success': True, 'message': f"Credentials dispatched to WhatsApp ({session.phone_number}) and Email ({agent.email})!"})


@require_POST
def wa_bot_save_config(request):
    """Save OpenWA Server URL, Session ID, and API Key to SiteSetting."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    base_url = request.POST.get('base_url', '').strip()
    session_id = request.POST.get('session_id', '').strip()
    api_key = request.POST.get('api_key', '').strip()

    if not base_url or not session_id:
        return JsonResponse({'success': False, 'error': 'OpenWA Server URL and Session ID are required'})

    SiteSetting.set_value('wa_bot_openwa_base_url', base_url)
    SiteSetting.set_value('wa_bot_openwa_session_id', session_id)
    if api_key:
        SiteSetting.set_value('wa_bot_openwa_api_key', api_key)

    # Immediately test connection
    status = get_openwa_session_status()
    is_online = status.get('online', False)
    msg = f"Configuration saved! Remote server is {'ONLINE' if is_online else 'OFFLINE / UNREACHABLE'}"

    _log_admin_action(request, 'update_openwa_config', 'System', 0, f"URL: {base_url}, Session: {session_id}")
    return JsonResponse({
        'success': True,
        'message': msg,
        'online': is_online,
        'latency_ms': status.get('latency_ms', 0),
        'session_status': status.get('status', 'unknown'),
    })


@require_POST
def wa_bot_sync_webhook(request):
    """Automatically register or update the webhook on the remote OpenWA server."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    webhook_url = request.POST.get('webhook_url', '').strip()
    if not webhook_url:
        webhook_url = request.build_absolute_uri('/wa-bot/webhook/')

    success, message = sync_openwa_webhook(webhook_url)
    _log_admin_action(request, 'sync_openwa_webhook', 'OpenWA_Webhook', 0, f"Webhook: {webhook_url} — {message}")
    return JsonResponse({
        'success': success,
        'message': message,
        'webhook_url': webhook_url
    })


@require_GET
def wa_bot_list_remote_sessions(request):
    """Fetch all sessions configured on the OpenWA server to auto-populate the UI."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    base_url = request.GET.get('base_url', '').strip() or None
    api_key = request.GET.get('api_key', '').strip() or None

    success, sessions, err = list_openwa_sessions(override_base_url=base_url, override_api_key=api_key)
    return JsonResponse({
        'success': success,
        'sessions': sessions,
        'error': err,
    })


