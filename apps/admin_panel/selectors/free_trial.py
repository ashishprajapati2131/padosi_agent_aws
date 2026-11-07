"""Read-only queries for the admin Free Trial pages (views/free_trial.py)."""

from django.db import connection


HISTORY_COLS = [
    "id",
    "agent_name",
    "agent_email",
    "agent_mobile",
    "promo_code",
    "trial_plan_name",
    "trial_duration_days",
    "trial_price_paid",
    "discount_amount",
    "discount_type",
    "source",
    "trial_started_at",
    "trial_ends_at",
]


def _dict_from_cursor(cursor):
    """Return list of dicts from a cursor with column names."""
    cols = [col[0] for col in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def count_free_trial_history():
    """Return the number of rows in free_trial_history."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM free_trial_history")
        return cursor.fetchone()[0]


def fetch_trial_promo_codes():
    """Return all free-trial promo codes (newest first) as dicts."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, code, discount_type, discount_value, is_active, is_free_trial,
                   trial_plan_name, trial_duration_days, trial_price_override, notes,
                   max_uses, times_used, expires_at, applicable_plan, created_at
            FROM promo_codes
            WHERE is_free_trial = 1
            ORDER BY created_at DESC
        """)
        return _dict_from_cursor(cursor)


def fetch_trial_agents():
    """Return up to 100 agents on the free_trial plan as dicts."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, fullname, email, mobile, trial_ends_at, upgrade_discount_percent
            FROM agents
            WHERE plan_type = 'free_trial'
            ORDER BY trial_ends_at DESC
            LIMIT 100
        """)
        return _dict_from_cursor(cursor)


def fetch_trial_stats(history_total, now_str):
    """Return the stats-card dict for the Free Trial page."""
    history_empty = history_total == 0
    with connection.cursor() as cursor:
        if history_empty:
            cursor.execute("SELECT COUNT(*) FROM agents WHERE plan_type = 'free_trial'")
            stat_total = cursor.fetchone()[0]
        else:
            stat_total = history_total

        cursor.execute(
            "SELECT COUNT(*) FROM agents WHERE plan_type = 'free_trial' AND trial_ends_at > %s",
            [now_str],
        )
        stat_active = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM agents WHERE plan_type = 'free_trial' AND trial_ends_at < %s",
            [now_str],
        )
        stat_expired = cursor.fetchone()[0]

        if history_empty:
            stat_by_promo = 0
            stat_by_ref = 0
            stat_revenue = (
                cursor.execute(
                    "SELECT COUNT(*) FROM agents WHERE plan_type = 'free_trial'"
                )
                or 0
            )
            cursor.execute("SELECT COUNT(*) FROM agents WHERE plan_type = 'free_trial'")
            stat_revenue = cursor.fetchone()[0] * 99
        else:
            cursor.execute(
                "SELECT COUNT(*) FROM free_trial_history WHERE source = 'promo'"
            )
            stat_by_promo = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM free_trial_history WHERE source = 'referral'"
            )
            stat_by_ref = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COALESCE(SUM(trial_price_paid), 0) FROM free_trial_history"
            )
            stat_revenue = float(cursor.fetchone()[0] or 0)

        cursor.execute(
            "SELECT COUNT(*) FROM promo_codes WHERE is_free_trial = 1 AND is_active = 1"
        )
        stat_codes_active = cursor.fetchone()[0]

    return {
        "total": stat_total,
        "active": stat_active,
        "expired": stat_expired,
        "by_promo": stat_by_promo,
        "by_ref": stat_by_ref,
        "revenue": stat_revenue,
        "codes_active": stat_codes_active,
    }


def fetch_monthly_stats(history_empty):
    """Return up to 12 monthly signup/revenue rows for the Chart.js chart."""
    with connection.cursor() as cursor:
        if history_empty:
            cursor.execute("""
                SELECT DATE_FORMAT(created_at, '%b %Y') as label,
                       YEAR(created_at) as yr, MONTH(created_at) as mo,
                       COUNT(*) as signups, SUM(99) as revenue
                FROM agents
                WHERE plan_type = 'free_trial'
                GROUP BY label, yr, mo
                ORDER BY yr, mo
                LIMIT 12
            """)
        else:
            cursor.execute("""
                SELECT DATE_FORMAT(created_at, '%b %Y') as label,
                       YEAR(created_at) as yr, MONTH(created_at) as mo,
                       COUNT(*) as signups, SUM(trial_price_paid) as revenue
                FROM free_trial_history
                GROUP BY label, yr, mo
                ORDER BY yr, mo
                LIMIT 12
            """)
        monthly_stats_raw = cursor.fetchall()
    return [
        {
            "label": r[0],
            "yr": r[1],
            "mo": r[2],
            "signups": r[3],
            "revenue": float(r[4] or 0),
        }
        for r in monthly_stats_raw
    ]


def fetch_promo_usage_summary(history_empty):
    """Return the top 10 promo codes by usage with revenue."""
    with connection.cursor() as cursor:
        if history_empty:
            cursor.execute("""
                SELECT code as promo_code, trial_plan_name, times_used as usages,
                       times_used * COALESCE(trial_price_override, 99) as revenue
                FROM promo_codes
                WHERE is_free_trial = 1 AND times_used > 0
                ORDER BY times_used DESC
                LIMIT 10
            """)
        else:
            cursor.execute("""
                SELECT promo_code, MAX(trial_plan_name) as trial_plan_name,
                       COUNT(*) as usages, SUM(trial_price_paid) as revenue
                FROM free_trial_history
                WHERE promo_code IS NOT NULL
                GROUP BY promo_code
                ORDER BY usages DESC
                LIMIT 10
            """)
        return [
            {
                "promo_code": r[0],
                "trial_plan_name": r[1],
                "usages": r[2],
                "revenue": float(r[3] or 0),
            }
            for r in cursor.fetchall()
        ]


def fetch_trial_history(history_empty):
    """Return every trial history row (or agents fallback) as dicts, newest first."""
    with connection.cursor() as cursor:
        if history_empty:
            cursor.execute("""
                SELECT id, fullname as agent_name, email as agent_email, mobile as agent_mobile,
                       NULL as promo_code, 'Standard Free Trial' as trial_plan_name,
                       30 as trial_duration_days, 99 as trial_price_paid,
                       0 as discount_amount, NULL as discount_type,
                       'direct' as source,
                       COALESCE(created_at, created_at) as trial_started_at,
                       trial_ends_at
                FROM agents
                WHERE plan_type = 'free_trial'
                ORDER BY created_at DESC
            """)
        else:
            cursor.execute("""
                SELECT id, agent_name, agent_email, agent_mobile,
                       promo_code, trial_plan_name, trial_duration_days, trial_price_paid,
                       discount_amount, discount_type, source, trial_started_at, trial_ends_at
                FROM free_trial_history
                ORDER BY created_at DESC
            """)
        history_rows = cursor.fetchall()
    return [dict(zip(HISTORY_COLS, r)) for r in history_rows]


def fetch_history_page(search, source, per_page, offset):
    """Return (total, rows) for one JSON page of trial history, filtered by search/source."""
    history_empty = count_free_trial_history() == 0

    if history_empty:
        # Fallback
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM agents WHERE plan_type = 'free_trial'")
            total = cursor.fetchone()[0]
            cursor.execute(
                """
                SELECT id, fullname, email, mobile,
                       NULL, 'Standard Free Trial', 30, 99, 0, NULL,
                       'direct', created_at, trial_ends_at
                FROM agents
                WHERE plan_type = 'free_trial'
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                [per_page, offset],
            )
            rows = cursor.fetchall()
    else:
        conditions = []
        params = []
        if search:
            conditions.append(
                "(agent_name LIKE %s OR agent_email LIKE %s OR promo_code LIKE %s)"
            )
            like = f"%{search}%"
            params.extend([like, like, like])
        if source:
            conditions.append("source = %s")
            params.append(source)

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) FROM free_trial_history {where_clause}", params
            )
            total = cursor.fetchone()[0]

            cursor.execute(
                f"""
                SELECT id, agent_name, agent_email, agent_mobile,
                       promo_code, trial_plan_name, trial_duration_days, trial_price_paid,
                       discount_amount, discount_type, source, trial_started_at, trial_ends_at
                FROM free_trial_history
                {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                params + [per_page, offset],
            )
            rows = cursor.fetchall()

    data = []
    for r in rows:
        item = dict(zip(HISTORY_COLS, r))
        # Convert datetimes to strings for JSON serialisation
        for key in ("trial_started_at", "trial_ends_at"):
            if item.get(key) and hasattr(item[key], "isoformat"):
                item[key] = item[key].isoformat()
        item["trial_price_paid"] = float(item.get("trial_price_paid") or 0)
        item["discount_amount"] = float(item.get("discount_amount") or 0)
        data.append(item)
    return total, data


def fetch_analytics_data():
    """Return (monthly, by_promo) chart lists; both empty when history is empty."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM free_trial_history")
        history_empty = cursor.fetchone()[0] == 0

        if history_empty:
            return [], []

        cursor.execute("""
            SELECT DATE_FORMAT(created_at, '%b %Y') as label,
                   COUNT(*) as signups,
                   SUM(trial_price_paid) as revenue,
                   SUM(CASE WHEN source='promo' THEN 1 ELSE 0 END) as via_promo,
                   SUM(CASE WHEN source='referral' THEN 1 ELSE 0 END) as via_referral,
                   SUM(CASE WHEN source='direct' THEN 1 ELSE 0 END) as via_direct
            FROM free_trial_history
            GROUP BY DATE_FORMAT(created_at, '%b %Y'), YEAR(created_at), MONTH(created_at)
            ORDER BY YEAR(created_at), MONTH(created_at)
            LIMIT 12
        """)
        monthly = [
            {
                "label": r[0],
                "signups": r[1],
                "revenue": float(r[2] or 0),
                "via_promo": r[3],
                "via_referral": r[4],
                "via_direct": r[5],
            }
            for r in cursor.fetchall()
        ]

        cursor.execute("""
            SELECT promo_code, trial_plan_name, COUNT(*) as uses, SUM(trial_price_paid) as revenue
            FROM free_trial_history
            WHERE promo_code IS NOT NULL
            GROUP BY promo_code, trial_plan_name
            ORDER BY uses DESC
            LIMIT 10
        """)
        by_promo = [
            {
                "promo_code": r[0],
                "trial_plan_name": r[1],
                "uses": r[2],
                "revenue": float(r[3] or 0),
            }
            for r in cursor.fetchall()
        ]

    return monthly, by_promo
