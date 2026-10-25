"""
Admin Panel Views for WhatsApp Agent Bot Monitoring
Provides views for Bot Sessions and Message Logs matching the custom Admin Panel theme.
"""

from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.wa_agent_bot.models import WaBotSession, WaBotMessageLog
from apps.home.models.site_setting import SiteSetting


def wa_bot_sessions_list(request):
    """Displays all WhatsApp bot registration sessions in Admin Panel."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    search_query = request.GET.get('q', '').strip()
    state_filter = request.GET.get('state', '').strip()

    sessions_qs = WaBotSession.objects.all().order_by('-last_message_at')

    if search_query:
        sessions_qs = sessions_qs.filter(phone_number__icontains=search_query)

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
    return render(request, 'admin/wa_bot_sessions.html', context)


def wa_bot_logs_list(request):
    """Displays WhatsApp bot message logs in Admin Panel."""
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
    return render(request, 'admin/wa_bot_logs.html', context)
