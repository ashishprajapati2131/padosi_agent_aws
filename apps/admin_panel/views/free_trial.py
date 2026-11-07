"""
apps/admin_panel/views/free_trial.py

Free Trial Manager — 100% Laravel parity.
Laravel source: app/Http/Controllers/Admin/AdminFreeTrialController.php

Routes implemented:
  GET  /padosi-admin/free-trial/                   → free_trial_index
  POST /padosi-admin/free-trial/update-config/     → ft_update_trial_config
  POST /padosi-admin/free-trial/update-discount/   → ft_update_upgrade_discount
  POST /padosi-admin/free-trial/update-referral-config/ → ft_update_referral_config
  POST /padosi-admin/free-trial/generate-promo/    → ft_generate_promo
  POST /padosi-admin/free-trial/promo/<id>/update/ → ft_update_promo
  POST /padosi-admin/free-trial/toggle-promo/      → ft_toggle_promo   (AJAX)
  POST /padosi-admin/free-trial/promo/<id>/delete/ → ft_delete_promo
  GET  /padosi-admin/free-trial/history/           → ft_history         (AJAX JSON)
  GET  /padosi-admin/free-trial/analytics-data/    → ft_analytics_data  (AJAX JSON)
"""

from apps.admin_panel.parsing import parse_int
from django.conf import settings
import json
import random
import string
from datetime import datetime
from django.utils import timezone as django_timezone

from django.contrib import messages
from django.utils.html import format_html
from django.core.paginator import Paginator
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from .dashboard import _get_admin_from_session
from ..selectors.free_trial import (
    count_free_trial_history,
    fetch_analytics_data,
    fetch_history_page,
    fetch_monthly_stats,
    fetch_promo_usage_summary,
    fetch_trial_agents,
    fetch_trial_history,
    fetch_trial_promo_codes,
    fetch_trial_stats,
)
from ..services import free_trial_service
from ..services.site_settings import get_setting

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_TRIAL_CONFIG = {
    'price': 99,
    'duration_days': 30,
    'badge': 'TRIAL',
    'description': 'Try before you commit — 30 days full access',
    'is_active': True,
}


def _dict_from_cursor(cursor):
    """Return list of dicts from a cursor with column names."""
    cols = [col[0] for col in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _generate_unique_code(prefix='TRIAL'):
    """Generate a unique promo code with given prefix + 6 random chars."""
    with connection.cursor() as cursor:
        for _ in range(20):
            suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            code = prefix.upper() + suffix
            cursor.execute("SELECT id FROM promo_codes WHERE code = %s", [code])
            if not cursor.fetchone():
                return code
    return prefix.upper() + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


def _log_activity(admin_id, description, model_type='AdminAction', model_id=None):
    """Shim over the shared audit logger (never raises)."""
    from apps.admin_panel.models import AdminActivityLog
    AdminActivityLog.log(description, model_type, model_id, admin_id=admin_id)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN PAGE  (GET /padosi-admin/free-trial/)
# ─────────────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def free_trial_index(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login_page')

    trial_config     = get_setting('trial_plan_config', DEFAULT_TRIAL_CONFIG)
    upgrade_discount = get_setting('trial_upgrade_discount', 20)
    referral_config  = get_setting('referral_config', {'eligibility': 'free_trial_only', 'count_free_trial': False})

    trial_promo_codes = fetch_trial_promo_codes()
    active_agents = fetch_trial_agents()

    now_dt = django_timezone.now()
    for a in active_agents:
        end_dt = a.get('trial_ends_at')
        if end_dt:
            if getattr(settings, 'USE_TZ', False):
                if django_timezone.is_naive(end_dt):
                    end_dt = django_timezone.make_aware(end_dt)
            else:
                if not django_timezone.is_naive(end_dt):
                    end_dt = django_timezone.make_naive(end_dt)
            a['is_expired'] = end_dt < now_dt
        else:
            a['is_expired'] = False

    # ── Stats ───────────────────────────────────────────────────────────
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # naive IST, like the DB columns

    history_total = count_free_trial_history()
    history_empty = (history_total == 0)
    stats = fetch_trial_stats(history_total, now_str)
    monthly_stats = fetch_monthly_stats(history_empty)
    promo_usage_summary = fetch_promo_usage_summary(history_empty)
    history = fetch_trial_history(history_empty)

    for h in history:
        end_dt = h.get('trial_ends_at')
        if end_dt:
            if getattr(settings, 'USE_TZ', False):
                if django_timezone.is_naive(end_dt):
                    end_dt = django_timezone.make_aware(end_dt)
            else:
                if not django_timezone.is_naive(end_dt):
                    end_dt = django_timezone.make_naive(end_dt)
            h['is_expired'] = end_dt < now_dt
        else:
            h['is_expired'] = True

    paginator = Paginator(history, 25)
    page_number = request.GET.get('page', 1)
    history_page = paginator.get_page(page_number)


    from datetime import timedelta
    tomorrow_date_str = (django_timezone.now() + timedelta(days=1)).strftime('%Y-%m-%d')

    context = {
        'admin':              admin,
        'trial_config':       trial_config,
        'upgrade_discount':   upgrade_discount,
        'tomorrow_date_str':  tomorrow_date_str,
        'referral_config':    referral_config,
        'trial_promo_codes':  trial_promo_codes,
        'active_agents':      active_agents,
        'stats':              stats,
        'monthly_stats':      monthly_stats,
        'promo_usage_summary': promo_usage_summary,
        'history':            history_page,
        'history_empty':      history_empty,
        # The fake-conversion test tool exists for local testing only.
        'show_test_tools':    settings.DEBUG,
    }
    return render(request, 'admin/free_trial/index.html', context)


# ─────────────────────────────────────────────────────────────────────────────
#  CONFIG ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def ft_update_trial_config(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login_page')

    price         = request.POST.get('price', '').strip()
    duration_days = request.POST.get('duration_days', '').strip()
    badge         = request.POST.get('badge', 'TRIAL').strip()
    description   = request.POST.get('description', '').strip()
    is_active     = bool(request.POST.get('is_active'))

    if not price or not duration_days:
        messages.error(request, 'Price and duration are required.')
        return redirect('admin_free_trial')

    try:
        price         = float(price)
        duration_days = int(duration_days)
    except ValueError:
        messages.error(request, 'Invalid price or duration.')
        return redirect('admin_free_trial')

    free_trial_service.update_trial_config(price, duration_days, badge, description, is_active)

    _log_activity(admin, 'Update Free Trial config', 'SiteSetting')
    messages.success(request, 'Free Trial configuration saved.')
    return redirect('admin_free_trial')


@require_http_methods(["POST"])
def ft_update_upgrade_discount(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login_page')

    discount = request.POST.get('upgrade_discount', '').strip()
    try:
        discount = float(discount)
        if not (0 <= discount <= 100):
            raise ValueError
    except ValueError:
        messages.error(request, 'Invalid discount value.')
        return redirect('admin_free_trial')

    updated_count = free_trial_service.update_upgrade_discount(discount)

    _log_activity(admin, f'Update trial upgrade discount to {discount}%', 'SiteSetting')
    messages.success(request, f'Discount updated to {discount}%. Applied to {updated_count} active agents.')
    return redirect('admin_free_trial')


@require_http_methods(["POST"])
def ft_update_referral_config(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login_page')

    eligibility       = request.POST.get('eligibility', 'free_trial_only')
    count_free_trial  = bool(request.POST.get('count_free_trial'))

    if eligibility not in ('all', 'free_trial_only'):
        messages.error(request, 'Invalid eligibility value.')
        return redirect('admin_free_trial')

    free_trial_service.update_referral_config(eligibility, count_free_trial)

    _log_activity(
        admin,
        f'Updated Referral Settings -> Eligibility: {eligibility}, '
        f'Count Free Trial: {"ON" if count_free_trial else "OFF"}',
        'SiteSetting',
    )
    messages.success(request, 'Referral configuration updated successfully.')
    return redirect('admin_free_trial')


@require_http_methods(["POST"])
def ft_force_test_credit(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login_page')

    # Inserts a fake active agent and applies referral rewards: local only.
    if not settings.DEBUG:
        messages.error(request, 'The fake-conversion test tool is disabled on the live site.')
        return redirect('admin_free_trial')

    agent_id_raw = request.POST.get('agent_id', '').strip()
    if not agent_id_raw:
        messages.error(request, 'The agent id field is required.')
        return redirect('admin_free_trial')

    try:
        agent_id = int(agent_id_raw)
    except ValueError:
        messages.error(request, 'The agent id must be an integer.')
        return redirect('admin_free_trial')

    agent_id = free_trial_service.force_test_credit(admin, agent_id, _log_activity)

    # 12. Flash message
    messages.success(request, f"Successfully FORCED +1 Fake Conversion to Agent ID {agent_id}. Rewards calculated and applied.")
    return redirect('admin_free_trial')


# ─────────────────────────────────────────────────────────────────────────────
#  TRIAL PROMO CODE CRUD
# ─────────────────────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def ft_generate_promo(request):
    """Generate a new trial promo code. Mirrors generateTrialPromoCode()."""
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login_page')

    prefix               = request.POST.get('prefix', 'TRIAL').strip() or 'TRIAL'
    trial_plan_name      = request.POST.get('trial_plan_name', '').strip() or None
    trial_duration_days  = request.POST.get('trial_duration_days', '').strip() or None
    trial_price_override = request.POST.get('trial_price_override', '').strip() or None
    max_uses             = request.POST.get('max_uses', '').strip() or None
    expires_at           = request.POST.get('expires_at', '').strip() or None
    discount_type        = request.POST.get('discount_type', 'fixed') or 'fixed'
    discount_value       = request.POST.get('discount_value', '0').strip() or '0'
    notes                = request.POST.get('notes', '').strip() or None

    # Sanitise
    if discount_type not in ('percentage', 'fixed'):
        discount_type = 'fixed'
    try:
        discount_value = float(discount_value)
    except ValueError:
        discount_value = 0.0

    try:
        trial_duration_days = int(trial_duration_days) if trial_duration_days else None
    except ValueError:
        trial_duration_days = None

    try:
        trial_price_override = float(trial_price_override) if trial_price_override else None
    except ValueError:
        trial_price_override = None

    try:
        max_uses = int(max_uses) if max_uses else None
    except ValueError:
        max_uses = None

    code = _generate_unique_code(prefix)

    new_id = free_trial_service.create_trial_promo(
        code, discount_type, discount_value, max_uses, expires_at,
        trial_plan_name, trial_duration_days, trial_price_override, notes,
    )

    _log_activity(admin, f'Generate Trial Promo Code: {code}', 'PromoCode', new_id)
    messages.success(request, format_html('Promo code <strong>{}</strong> created! Share this with agents.', code))
    return redirect('admin_free_trial')


@require_http_methods(["POST"])
def ft_update_promo(request, promo_id):
    """Edit an existing trial promo code. Mirrors updateTrialPromoCode()."""
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login_page')

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, code FROM promo_codes WHERE id = %s AND is_free_trial = 1",
            [promo_id],
        )
        row = cursor.fetchone()

    if not row:
        messages.error(request, 'Trial promo code not found.')
        return redirect('admin_free_trial')

    code_str = row[1]

    trial_plan_name      = request.POST.get('trial_plan_name', '').strip() or None
    trial_duration_days  = request.POST.get('trial_duration_days', '').strip() or None
    trial_price_override = request.POST.get('trial_price_override', '').strip() or None
    max_uses             = request.POST.get('max_uses', '').strip() or None
    expires_at           = request.POST.get('expires_at', '').strip() or None
    discount_type        = request.POST.get('discount_type', 'fixed') or 'fixed'
    discount_value       = request.POST.get('discount_value', '0').strip() or '0'
    notes                = request.POST.get('notes', '').strip() or None

    if discount_type not in ('percentage', 'fixed'):
        discount_type = 'fixed'
    try:
        discount_value = float(discount_value)
    except ValueError:
        discount_value = 0.0
    try:
        trial_duration_days = int(trial_duration_days) if trial_duration_days else None
    except ValueError:
        trial_duration_days = None
    try:
        trial_price_override = float(trial_price_override) if trial_price_override else None
    except ValueError:
        trial_price_override = None
    try:
        max_uses = int(max_uses) if max_uses else None
    except ValueError:
        max_uses = None
    # datetime-local comes as "YYYY-MM-DDTHH:MM" — convert to MySQL timestamp
    if expires_at and 'T' in expires_at:
        expires_at = expires_at.replace('T', ' ') + ':00'

    free_trial_service.update_trial_promo(
        promo_id, discount_type, discount_value, max_uses, expires_at,
        trial_plan_name, trial_duration_days, trial_price_override, notes,
    )

    _log_activity(admin, f'Updated Trial Promo Code: {code_str}', 'PromoCode', promo_id)
    messages.success(request, format_html('Promo code <strong>{}</strong> updated successfully!', code_str))
    return redirect('admin_free_trial')


@csrf_protect
@require_http_methods(["POST"])
def ft_toggle_promo(request):
    """AJAX toggle for trial promo code active state. Returns JSON."""
    admin = _get_admin_from_session(request)
    if not admin:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
        promo_id = int(data.get('id', 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'Invalid request'}, status=400)

    new_status = free_trial_service.toggle_trial_promo(promo_id)
    if new_status is None:
        return JsonResponse({'success': False, 'message': 'Not found'}, status=404)

    return JsonResponse({'success': True, 'is_active': bool(new_status)})


@require_http_methods(["POST"])
def ft_delete_promo(request, promo_id):
    """Hard-delete a trial promo code. Mirrors deleteTrialPromoCode()."""
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login_page')

    code_str = free_trial_service.delete_trial_promo(promo_id)
    if code_str is None:
        messages.error(request, 'Trial promo code not found.')
        return redirect('admin_free_trial')

    _log_activity(admin, f'Deleted Trial Promo Code: {code_str}', 'PromoCode')
    messages.success(request, f'Promo code {code_str} deleted.')
    return redirect('admin_free_trial')


# ─────────────────────────────────────────────────────────────────────────────
#  HISTORY  (AJAX/paginated JSON)
# ─────────────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def ft_history(request):
    """
    AJAX endpoint — returns paginated JSON of free_trial_history rows.
    Falls back to agents table if history is empty.
    Mirrors AdminFreeTrialController::history().
    """
    admin = _get_admin_from_session(request)
    if not admin:
        return JsonResponse({'success': False}, status=401)

    search    = request.GET.get('search', '').strip()
    source    = request.GET.get('source', '').strip()
    page      = max(1, parse_int(request.GET.get('page'), 1))
    per_page  = 20
    offset    = (page - 1) * per_page

    total, data = fetch_history_page(search, source, per_page, offset)

    total_pages = max(1, (total + per_page - 1) // per_page)
    return JsonResponse({
        'data':        data,
        'total':       total,
        'page':        page,
        'per_page':    per_page,
        'total_pages': total_pages,
    })


# ─────────────────────────────────────────────────────────────────────────────
#  ANALYTICS DATA  (AJAX JSON for Chart.js)
# ─────────────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def ft_analytics_data(request):
    """
    AJAX endpoint — monthly stats + top promo breakdown for Chart.js.
    Mirrors AdminFreeTrialController::analyticsData().
    """
    admin = _get_admin_from_session(request)
    if not admin:
        return JsonResponse({'success': False}, status=401)

    monthly, by_promo = fetch_analytics_data()

    return JsonResponse({'monthly': monthly, 'by_promo': by_promo})
