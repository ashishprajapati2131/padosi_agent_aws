"""
apps/admin_panel/selectors/referrals.py

Read-only queries for the admin referrals page (views/referrals.py).
"""

from django.db import connection


def _dict_from_cursor(cursor):
    cols = [col[0] for col in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def fetch_referral_stats():
    """Return the global referral KPI stats dict."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM referral_codes")
        total_codes = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM referral_codes WHERE is_active = 1")
        active_codes = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM referral_usages")
        total_signups = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM referral_usages WHERE status = 'converted'"
        )
        converted = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM referral_usages WHERE status != 'converted'"
        )
        pending = cursor.fetchone()[0]

        conv_rate = (
            round((converted / total_signups * 100), 1) if total_signups > 0 else 0
        )

        cursor.execute(
            "SELECT COUNT(*) FROM referral_codes WHERE reward_type = 'discount_25'"
        )
        rewards_25pct = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM referral_codes WHERE reward_type = 'discount_50'"
        )
        rewards_50pct = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM referral_codes WHERE reward_type = 'pro_plan_1rs'"
        )
        rewards_pro1rs = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM referral_codes "
            "WHERE reward_type IS NOT NULL AND reward_claimed = 0"
        )
        unclaimed = cursor.fetchone()[0]

    return {
        "total_codes": total_codes,
        "active_codes": active_codes,
        "total_signups": total_signups,
        "converted": converted,
        "pending": pending,
        "conv_rate": conv_rate,
        "rewards_25pct": rewards_25pct,
        "rewards_50pct": rewards_50pct,
        "rewards_pro1rs": rewards_pro1rs,
        "unclaimed": unclaimed,
    }


def fetch_converted_plan_breakdown():
    """Return converted referred agents grouped by plan_type, each row with cnt and pct."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT a.plan_type, COUNT(*) as cnt
            FROM referral_usages ru
            JOIN agents a ON a.id = ru.referred_agent_id
            WHERE ru.status = 'converted'
            GROUP BY a.plan_type
        """)
        plan_breakdown = _dict_from_cursor(cursor)

    # Compute total_plan = sum of all cnt values (matches Laravel's $planBreakdown->sum('cnt'))
    total_plan = sum(row["cnt"] for row in plan_breakdown)
    for row in plan_breakdown:
        row["pct"] = round((row["cnt"] / total_plan) * 100) if total_plan > 0 else 0
    return plan_breakdown


def fetch_codes_page(
    search, plan_filter, reward_filter, status_filter, page_num, per_page
):
    """Return (codes, total_filtered, total_pages) for one filtered page of referral codes."""
    where_parts = []
    params = []

    if search:
        where_parts.append("""
            (rc.code LIKE %s
             OR a.fullname LIKE %s
             OR a.email LIKE %s
             OR a.mobile LIKE %s)
        """)
        like = f"%{search}%"
        params += [like, like, like, like]

    if plan_filter == "free_trial":
        where_parts.append("a.plan_type = 'free_trial'")
    elif plan_filter == "paid":
        where_parts.append("a.plan_type != 'free_trial'")

    if reward_filter == "none":
        where_parts.append("rc.reward_type IS NULL")
    elif reward_filter == "unclaimed":
        where_parts.append("rc.reward_type IS NOT NULL AND rc.reward_claimed = 0")
    elif reward_filter == "claimed":
        where_parts.append("rc.reward_claimed = 1")

    if status_filter == "active":
        where_parts.append("rc.is_active = 1")
    elif status_filter == "inactive":
        where_parts.append("rc.is_active = 0")

    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    with connection.cursor() as cursor:
        # ── Count total for pagination ──
        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM referral_codes rc
            LEFT JOIN agents a ON a.id = rc.agent_id
            {where_sql}
        """,
            params,
        )
        total_codes_filtered = cursor.fetchone()[0]
        total_pages = max(1, (total_codes_filtered + per_page - 1) // per_page)
        offset = (page_num - 1) * per_page

        # ── Agent codes with full detail ──
        cursor.execute(
            f"""
            SELECT rc.id, rc.agent_id, rc.code, rc.is_active, rc.total_referrals,
                   rc.pending_referrals, rc.clicks, rc.reward_type,
                   rc.reward_claimed, rc.reward_claimed_at, rc.created_at,
                   a.fullname, a.email, a.mobile, a.plan_type, a.status as agent_status
            FROM referral_codes rc
            LEFT JOIN agents a ON a.id = rc.agent_id
            {where_sql}
            ORDER BY rc.total_referrals DESC
            LIMIT %s OFFSET %s
        """,
            params + [per_page, offset],
        )
        all_codes = _dict_from_cursor(cursor)

    return all_codes, total_codes_filtered, total_pages


def fetch_usages_by_code_id(code_ids):
    """Return {referral_code_id: [usage rows]} for the given code ids."""
    referred_map = {}
    if code_ids:
        placeholders = ",".join(["%s"] * len(code_ids))
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT ru.id, ru.referral_code_id, ru.referred_agent_id,
                       ru.referred_agent_name, ru.status, ru.converted_at, ru.created_at,
                       a.fullname as ref_fullname, a.email as ref_email,
                       a.plan_type as ref_plan_type, a.status as ref_status,
                       a.created_at as ref_created_at
                FROM referral_usages ru
                LEFT JOIN agents a ON a.id = ru.referred_agent_id
                WHERE ru.referral_code_id IN ({placeholders})
                ORDER BY ru.created_at DESC
            """,
                code_ids,
            )
            for row in _dict_from_cursor(cursor):
                cid = row["referral_code_id"]
                referred_map.setdefault(cid, []).append(row)
    return referred_map


def fetch_recent_usages():
    """Return the 30 most recent referral usages with referrer/referred names."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT ru.id, ru.referred_agent_name, ru.status, ru.created_at,
                   ru.converted_at,
                   a_ref.fullname  as referred_fullname,
                   a_ref.plan_type as referred_plan_type,
                   a_ref.status    as referred_status,
                   a_rer.fullname  as referrer_fullname
            FROM referral_usages ru
            LEFT JOIN agents a_ref ON a_ref.id = ru.referred_agent_id
            LEFT JOIN agents a_rer ON a_rer.id = ru.referrer_agent_id
            ORDER BY ru.created_at DESC
            LIMIT 30
        """)
        return _dict_from_cursor(cursor)
