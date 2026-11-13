"""
WhatsApp Agent Bot — Interactive Web Simulator Views
Provides a live WhatsApp Web mockup in the browser for testing.
"""

import json
import logging
from functools import wraps
from django.conf import settings
from django.http import Http404, JsonResponse, HttpResponse
from django.middleware.csrf import get_token
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST, require_GET
from apps.home.models.site_setting import SiteSetting
from .models import WaBotSession, WaBotMessageLog
from .views import is_wa_bot_enabled
from .services.state_machine import process_message
from .services.payment_service import activate_agent_subscription_after_payment

logger = logging.getLogger(__name__)

SIMULATOR_PHONE = "919876543210"


def _admin_required(view):
    """Simulator is an admin-only tool: require a valid admin session."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not settings.DEBUG:
            # Simulator creates real users/agents/payment links: never in production.
            raise Http404
        from apps.admin_panel.auth import _get_admin_from_session
        if not _get_admin_from_session(request):
            return JsonResponse({'error': 'Admin login required'}, status=403)
        return view(request, *args, **kwargs)
    return wrapper


@_admin_required
@require_GET
def simulator_page(request):
    """Renders the WhatsApp Web Simulator page."""
    csrf_token = get_token(request)
    enabled = is_wa_bot_enabled()
    session = WaBotSession.objects.filter(phone_number=SIMULATOR_PHONE).first()
    
    # Get recent messages if any
    recent_logs = []
    max_log_id = 0
    if session:
        logs = session.message_logs.order_by('created_at')[:50]
        for log in logs:
            max_log_id = max(max_log_id, log.id)
            recent_logs.append({
                'id': log.id,
                'direction': log.direction,
                'content': log.content,
                'time': log.created_at.strftime('%I:%M %p'),
            })

    # No request passed: the old page ran no context processors (they query the DB).
    html = render_to_string(
        'wa_agent_bot/simulator.html',
        {
            'csrf_token': csrf_token,
            'enabled': enabled,
            'phone': SIMULATOR_PHONE,
            'recent_logs': recent_logs,
            'max_log_id': max_log_id,
        },
    )
    return HttpResponse(html, content_type='text/html')


@_admin_required
@require_POST
def simulator_send(request):
    """Processes a simulated user message from the browser UI."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    text = body.get('message', '').strip()
    phone = SIMULATOR_PHONE

    if not is_wa_bot_enabled():
        return JsonResponse({'status': 'disabled', 'message': 'WhatsApp Bot is paused via Admin Panel'})

    session, _ = WaBotSession.objects.get_or_create(
        phone_number=phone,
        defaults={
            'state': WaBotSession.STATE_WELCOME,
            'registration_data': {},
            'session_context': {},
        }
    )
    session.update_last_activity()

    # Log incoming
    WaBotMessageLog.objects.create(
        session=session,
        phone_number=phone,
        direction=WaBotMessageLog.DIRECTION_IN,
        category='simulator',
        status=WaBotMessageLog.STATUS_RECEIVED,
        content=text[:2000],
        state_at_time=session.state,
    )

    # Process via state machine
    try:
        reply = process_message(session, text)
    except Exception as e:
        logger.error(f"[WA-Bot-Simulator] Error processing message: {e}", exc_info=True)
        reply = "Sorry, an error occurred. Please try typing *restart*."

    # Log outgoing
    WaBotMessageLog.objects.create(
        session=session,
        phone_number=phone,
        direction=WaBotMessageLog.DIRECTION_OUT,
        category='simulator',
        content=reply[:5000],
        state_at_time=session.state,
    )
    session.save()

    return JsonResponse({
        'status': 'processed',
        'reply': reply,
        'state': session.state,
        'phone': phone,
    })


@_admin_required
@require_POST
def simulator_reset(request):
    """Clears the session for the simulator phone."""
    phone = SIMULATOR_PHONE

    WaBotSession.objects.filter(phone_number=phone).delete()
    return JsonResponse({'success': True, 'message': 'Session reset'})


@_admin_required
@require_POST
def simulator_payment(request):
    """Simulates payment completion for the current session."""
    if not settings.DEBUG:
        # Activating a subscription without payment must never be reachable in production.
        return JsonResponse({'success': False, 'message': 'Payment simulation is disabled in production'}, status=403)
    phone = SIMULATOR_PHONE

    session = WaBotSession.objects.filter(phone_number=phone).first()
    if not session:
        return JsonResponse({'success': False, 'message': 'No session found'})

    sub_id = session.registration_data.get('subscription_id')
    if not sub_id:
        return JsonResponse({'success': False, 'message': 'No pending subscription found. Please select a plan first.'})

    success, msg = activate_agent_subscription_after_payment(sub_id, payment_id="pay_simulated_browser")
    
    # Fetch credentials message logged
    last_log = session.message_logs.filter(direction=WaBotMessageLog.DIRECTION_OUT).order_by('-created_at').first()
    reply = last_log.content if last_log else msg

    return JsonResponse({
        'success': success,
        'message': msg,
        'reply': reply,
    })


@_admin_required
@require_POST
def simulator_toggle(request):
    """Toggles the Master Switch ON/OFF."""
    val = SiteSetting.get_value('wa_agent_bot_enabled', True)
    if isinstance(val, str):
        current = val.strip().lower() in ('1', 'true', 'yes', 'on', 'active', 't')
    else:
        current = bool(val)
    new_val = not current
    SiteSetting.set_value('wa_agent_bot_enabled', '1' if new_val else '0', group='general')
    return JsonResponse({'success': True, 'enabled': new_val})


@_admin_required
@require_GET
def simulator_poll(request):
    """
    Polls for new outgoing messages for the simulator session.
    Allows real-time display of asynchronous credentials, webhook confirmations,
    or admin approval messages without needing manual reload.
    """
    phone = SIMULATOR_PHONE
    try:
        last_id = int(request.GET.get('last_id', 0) or 0)
    except (TypeError, ValueError):
        last_id = 0

    session = WaBotSession.objects.filter(phone_number=phone).first()
    if not session:
        return JsonResponse({'messages': [], 'last_id': last_id, 'state': 'welcome', 'is_logged_in': False})

    new_logs = session.message_logs.filter(id__gt=last_id, direction=WaBotMessageLog.DIRECTION_OUT).order_by('id')
    messages = []
    max_id = last_id
    for log in new_logs:
        max_id = max(max_id, log.id)
        messages.append({
            'id': log.id,
            'direction': 'in',
            'content': log.content,
            'time': log.created_at.strftime('%I:%M %p'),
        })

    return JsonResponse({
        'messages': messages,
        'last_id': max_id,
        'state': session.state,
        'is_logged_in': session.is_logged_in,
    })
