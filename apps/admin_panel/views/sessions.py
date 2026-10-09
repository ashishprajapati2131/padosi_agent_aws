"""
Admin module #15 — Session & Device Management.

Lists active admin sessions stored in the custom `user_sessions` table
(the same table the admin login writes to), showing IP, device/browser,
last activity and expiry, with a "Revoke" (force-logout) action.

Read-only over existing data + a safe row delete. No schema changes.
"""
import datetime

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.db import connection
from django.views.decorators.http import require_POST

from apps.admin_panel.models.user_session import UserSession, UserSessionData
from apps.admin_panel.models.admin_auth import Admin
from apps.admin_panel.models.admin_activity_log import AdminActivityLog
from apps.admin_panel.views.dashboard import _get_admin_from_session, ADMIN_SESSION_COOKIE


def _parse_user_agent(ua):
    """Return a short, friendly 'Browser on OS' label from a UA string."""
    if not ua:
        return 'Unknown device'
    ua_l = ua.lower()
    if 'edg/' in ua_l or 'edge' in ua_l:
        browser = 'Edge'
    elif 'chrome' in ua_l and 'chromium' not in ua_l:
        browser = 'Chrome'
    elif 'firefox' in ua_l:
        browser = 'Firefox'
    elif 'safari' in ua_l:
        browser = 'Safari'
    elif 'okhttp' in ua_l or 'dart' in ua_l or 'flutter' in ua_l:
        browser = 'Mobile App'
    else:
        browser = 'Browser'

    if 'android' in ua_l:
        os_name = 'Android'
    elif 'iphone' in ua_l or 'ipad' in ua_l or 'ios' in ua_l:
        os_name = 'iOS'
    elif 'windows' in ua_l:
        os_name = 'Windows'
    elif 'mac os' in ua_l or 'macintosh' in ua_l:
        os_name = 'macOS'
    elif 'linux' in ua_l:
        os_name = 'Linux'
    else:
        os_name = 'Unknown OS'
    return f'{browser} on {os_name}'


def _admin_id_fallback_map(session_ids):
    """For sessions whose user_sessions.admin_id is NULL, read it from user_session_data."""
    result = {}
    if not session_ids:
        return result
    rows = (
        UserSessionData.objects
        .filter(session_id__in=list(session_ids), data_key='admin_id')
        .values_list('session_id', 'data_value')
    )
    for sid, val in rows:
        try:
            result[sid] = int(val)
        except (TypeError, ValueError):
            continue
    return result


def sessions_index(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    current_token = request.COOKIES.get(ADMIN_SESSION_COOKIE)
    now = datetime.datetime.now()

    session_rows = list(UserSession.objects.all().order_by('-last_activity', '-id')[:500])

    # Resolve admin for rows where admin_id column is NULL.
    null_admin_sids = [s.id for s in session_rows if not s.admin_id]
    fallback = _admin_id_fallback_map(null_admin_sids)

    admins = {a.id: a for a in Admin.objects.all()}

    items = []
    active_count = 0
    for s in session_rows:
        a_id = s.admin_id or fallback.get(s.id)
        admin_obj = admins.get(a_id) if a_id else None
        is_expired = bool(s.expires_at and s.expires_at < now)
        if not is_expired:
            active_count += 1
        token = s.session_token or ''
        items.append({
            'id': s.id,
            'admin_name': admin_obj.name if admin_obj else '—',
            'admin_email': admin_obj.email if admin_obj else '',
            'admin_role': admin_obj.role if admin_obj else '',
            'ip_address': s.ip_address or '—',
            'device': _parse_user_agent(s.user_agent),
            'user_agent': s.user_agent or '',
            'last_activity': s.last_activity,
            'expires_at': s.expires_at,
            'is_expired': is_expired,
            'is_current': bool(current_token and token == current_token),
            'token_tail': token[-8:] if token else '',
        })

    stats = {
        'total': len(items),
        'active': active_count,
        'expired': len(items) - active_count,
    }
    return render(request, 'admin/sessions.html', {'sessions': items, 'stats': stats})


@require_POST
def sessions_revoke(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    session_id = request.POST.get('id')
    if not session_id:
        return JsonResponse({'success': False, 'message': 'Session id required.'}, status=400)

    try:
        session_id = int(session_id)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Invalid session id.'}, status=400)

    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM user_sessions WHERE id = %s LIMIT 1", [session_id])
        if not cursor.fetchone():
            return JsonResponse({'success': False, 'message': 'Session not found.'}, status=404)
        cursor.execute("DELETE FROM user_session_data WHERE session_id = %s", [session_id])
        cursor.execute("DELETE FROM user_sessions WHERE id = %s", [session_id])

    AdminActivityLog.log(
        f'Revoked admin session #{session_id}',
        'UserSession', session_id, request=request,
    )
    return JsonResponse({'success': True, 'message': 'Session revoked.'})
