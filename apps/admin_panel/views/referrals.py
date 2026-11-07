"""
apps/admin_panel/views/referrals.py

Admin Referral Analytics & Management.
Mirrors AdminFreeTrialController::referrals() and related methods from Laravel.

Routes:
    GET  /admin/referrals/                          → admin_referrals_index
    POST /admin/referrals/toggle-code/              → admin_referrals_toggle_code   (AJAX JSON)
    POST /admin/referrals/<id>/mark-claimed/        → admin_referrals_mark_claimed
    POST /admin/referrals/generate-missing-codes/   → admin_referrals_generate_missing
    POST /admin/referrals/update-tiers/             → admin_referrals_update_tiers
"""

from apps.admin_panel.parsing import parse_int
import json

from django.contrib import messages
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .dashboard import _get_admin_from_session
from ..selectors.referrals import (
    fetch_codes_page,
    fetch_converted_plan_breakdown,
    fetch_recent_usages,
    fetch_referral_stats,
    fetch_usages_by_code_id,
)
from ..services.referral_service import (
    REFERRAL_TIERS,
    generate_referral_code_for_agent,
    get_tier_for_count,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _dict_from_cursor(cursor):
    cols = [col[0] for col in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _log_activity(admin_id, description, model_type='AdminAction', model_id=None):
    """Shim over the shared audit logger (never raises)."""
    from apps.admin_panel.models import AdminActivityLog
    AdminActivityLog.log(description, model_type, model_id, admin_id=admin_id)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN PAGE  GET /admin/referrals/
# ─────────────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def admin_referrals_index(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login_page')

    search       = request.GET.get('search', '').strip()
    plan_filter  = request.GET.get('plan_type', '').strip()
    reward_filter = request.GET.get('reward_status', '').strip()
    status_filter = request.GET.get('status', '').strip()
    page_num     = max(1, parse_int(request.GET.get('page'), 1))
    per_page     = 20

    stats = fetch_referral_stats()
    plan_breakdown = fetch_converted_plan_breakdown()
    all_codes, total_codes_filtered, total_pages = fetch_codes_page(
        search, plan_filter, reward_filter, status_filter, page_num, per_page,
    )
    referred_map = fetch_usages_by_code_id([c['id'] for c in all_codes])
    recent_usages = fetch_recent_usages()

    # Build pagination object
    pagination = {
        'current_page':  page_num,
        'total_pages':   total_pages,
        'total_items':   total_codes_filtered,
        'has_prev':      page_num > 1,
        'has_next':      page_num < total_pages,
        'prev_page':     page_num - 1,
        'next_page':     page_num + 1,
        'page_range':    range(max(1, page_num - 2), min(total_pages + 1, page_num + 3)),
    }

    # Attach referred usages and tier labels to each code
    for code in all_codes:
        code['usages']    = referred_map.get(code['id'], [])
        code['converted'] = sum(1 for u in code['usages'] if u['status'] == 'converted')
        code['pending_c'] = sum(1 for u in code['usages'] if u['status'] != 'converted')
        tier = get_tier_for_count(code['total_referrals'] or 0)
        code['tier'] = tier

    return render(request, 'admin/referrals/index.html', {
        'stats':         stats,
        'all_codes':     all_codes,
        'recent_usages': recent_usages,
        'plan_breakdown': plan_breakdown,
        'pagination':    pagination,
        'tiers':         REFERRAL_TIERS,
        # Filter echo-back
        'search':        search,
        'plan_filter':   plan_filter,
        'reward_filter': reward_filter,
        'status_filter': status_filter,
    })


# ─────────────────────────────────────────────────────────────────────────────
#  TOGGLE CODE  POST /admin/referrals/toggle-code/  (AJAX JSON)
# ─────────────────────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def admin_referrals_toggle_code(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    try:
        body = json.loads(request.body)
        code_id = int(body.get('id', 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid payload'}, status=400)

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, is_active FROM referral_codes WHERE id = %s LIMIT 1",
            [code_id],
        )
        row = cursor.fetchone()
        if not row:
            return JsonResponse({'success': False, 'error': 'Not found'}, status=404)

        new_status = 0 if row[1] else 1
        cursor.execute(
            "UPDATE referral_codes SET is_active = %s, updated_at = NOW() WHERE id = %s",
            [new_status, code_id],
        )

    return JsonResponse({'success': True, 'is_active': bool(new_status)})


# ─────────────────────────────────────────────────────────────────────────────
#  MARK CLAIMED  POST /admin/referrals/<id>/mark-claimed/
# ─────────────────────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def admin_referrals_mark_claimed(request, code_id):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login_page')

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, agent_id FROM referral_codes WHERE id = %s LIMIT 1",
            [code_id],
        )
        row = cursor.fetchone()
        if not row:
            messages.error(request, 'Referral code not found.')
            return redirect('admin_referrals_index')

        agent_id = row[1]
        cursor.execute(
            """
            UPDATE referral_codes
            SET reward_claimed = 1, reward_claimed_at = NOW(), updated_at = NOW()
            WHERE id = %s
            """,
            [code_id],
        )

    _log_activity(
        admin,
        f"Mark referral reward claimed for agent #{agent_id}",
        'ReferralCode',
        code_id,
    )
    messages.success(request, 'Reward marked as claimed.')
    return redirect('admin_referrals_index')


# ─────────────────────────────────────────────────────────────────────────────
#  GENERATE MISSING CODES  POST /admin/referrals/generate-missing-codes/
# ─────────────────────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def admin_referrals_generate_missing(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login_page')

    count = 0
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, fullname FROM agents WHERE status = 'active'"
        )
        agents = _dict_from_cursor(cursor)

        for agent in agents:
            cursor.execute(
                "SELECT COUNT(*) FROM referral_codes WHERE agent_id = %s",
                [agent['id']],
            )
            if cursor.fetchone()[0] == 0:
                generate_referral_code_for_agent(cursor, agent['id'], agent['fullname'])
                count += 1

    _log_activity(admin, f"Generated {count} missing referral codes for active agents.", 'ReferralCode')
    messages.success(request, f'Generated {count} missing referral codes for active agents.')
    return redirect('admin_referrals_index')


# ─────────────────────────────────────────────────────────────────────────────
#  UPDATE TIERS  POST /admin/referrals/update-tiers/
#  Mirrors AdminFreeTrialController::updateReferralTiers()
# ─────────────────────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def admin_referrals_update_tiers(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect('admin_login_page')

    try:
        config = {
            'tier1_min':    int(request.POST.get('tier1_min', 5)),
            'tier1_reward': 'discount_25',
            'tier2_min':    int(request.POST.get('tier2_min', 10)),
            'tier2_reward': 'discount_50',
            'tier3_min':    int(request.POST.get('tier3_min', 15)),
            'tier3_reward': 'pro_plan_1rs',
        }
    except (TypeError, ValueError):
        messages.error(request, "Tier thresholds must be whole numbers. Nothing was saved.")
        return redirect("admin_referrals_index")

    with connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO site_settings (`key`, `value`, `group`, created_at, updated_at)
            VALUES ('referral_tier_config', %s, 'referral', NOW(), NOW())
            ON DUPLICATE KEY UPDATE `value` = VALUES(`value`), updated_at = NOW()
        """, [__import__('json').dumps(config)])

    _log_activity(admin, 'Update referral tier config', 'SiteSetting')
    messages.success(request, 'Referral tier configuration updated.')
    return redirect('admin_referrals_index')
