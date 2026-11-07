"""Read-only queries for the admin revenue dashboard.

Each function takes the caller's cursor so the view's connection (patched in tests) is the one used.
"""


def fetch_monthly_revenue(cursor, now):
    """Return per-month revenue rows by plan for the 12 months before `now`."""
    cursor.execute(
        """
            SELECT
                DATE_FORMAT(s.created_at, '%b %Y')  AS label,
                YEAR(s.created_at)                  AS yr,
                MONTH(s.created_at)                 AS mo,
                SUM(CASE WHEN LOWER(s.selected_plan) LIKE '%%professional%%'
                         THEN COALESCE(s.registration_amount, 0) ELSE 0 END) AS professional,
                SUM(CASE WHEN LOWER(s.selected_plan) LIKE '%%starter%%'
                         THEN COALESCE(s.registration_amount, 0) ELSE 0 END) AS starter,
                SUM(CASE WHEN LOWER(s.selected_plan) LIKE '%%trial%%'
                         THEN COALESCE(s.registration_amount, 0) ELSE 0 END) AS trial,
                SUM(COALESCE(s.registration_amount, 0))                       AS total
            FROM agent_subscriptions s
            WHERE s.created_at >= DATE_SUB(%s, INTERVAL 12 MONTH)
            AND LOWER(s.payment_status) = 'completed'
            GROUP BY label, yr, mo
            ORDER BY yr ASC, mo ASC
        """,
        [now],
    )  # naive IST columns; UTC_TIMESTAMP() is 5h30m behind
    cols = [col[0] for col in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def fetch_active_agent_counts(cursor):
    """Return (professional, starter, trial) counts of agents not in an inactive status."""
    excluded_statuses = ("suspended", "incomplete", "pending_payment", "pending")
    placeholders = ",".join(["%s"] * len(excluded_statuses))

    cursor.execute(
        f"SELECT COUNT(*) FROM agents WHERE plan_type = 'professional' AND status NOT IN ({placeholders})",
        excluded_statuses,
    )
    prof_count = cursor.fetchone()[0]

    # Paid signups are stored as 'starter'; Paldi-challenge winners as 'basic'.
    cursor.execute(
        f"SELECT COUNT(*) FROM agents WHERE plan_type IN ('basic', 'starter') AND status NOT IN ({placeholders})",
        excluded_statuses,
    )
    starter_count = cursor.fetchone()[0]

    cursor.execute(
        f"SELECT COUNT(*) FROM agents WHERE plan_type = 'free_trial' AND status NOT IN ({placeholders})",
        excluded_statuses,
    )
    trial_count = cursor.fetchone()[0]

    return prof_count, starter_count, trial_count


def fetch_plan_revenue_totals(cursor):
    """Return all-time completed revenue as (professional, starter, trial, total)."""
    cursor.execute(
        "SELECT SUM(registration_amount) FROM agent_subscriptions WHERE payment_status = 'completed' AND LOWER(selected_plan) LIKE '%%professional%%'"
    )
    pro_revenue = cursor.fetchone()[0] or 0

    cursor.execute(
        "SELECT SUM(registration_amount) FROM agent_subscriptions WHERE payment_status = 'completed' AND LOWER(selected_plan) LIKE '%%starter%%'"
    )
    starter_revenue = cursor.fetchone()[0] or 0

    cursor.execute(
        "SELECT SUM(registration_amount) FROM agent_subscriptions WHERE payment_status = 'completed' AND LOWER(selected_plan) LIKE '%%trial%%'"
    )
    trial_revenue = cursor.fetchone()[0] or 0

    # All completed payments, so plans outside the three named ones (e.g. Exclusive) are counted.
    cursor.execute(
        "SELECT SUM(registration_amount) FROM agent_subscriptions WHERE payment_status = 'completed'"
    )
    total_revenue = float(cursor.fetchone()[0] or 0)

    return pro_revenue, starter_revenue, trial_revenue, total_revenue


def fetch_raw_mrr(cursor, now_ist):
    """Return (professional, starter) raw monthly recurring revenue for subscriptions live at `now_ist`."""
    mrr_query = """
            SELECT SUM(s.registration_amount / GREATEST(1, TIMESTAMPDIFF(MONTH, s.starts_at, COALESCE(s.expires_at, DATE_ADD(s.starts_at, INTERVAL 12 MONTH))))) as monthly
            FROM agent_subscriptions s
            JOIN agents a ON s.agent_id = a.id
            WHERE a.plan_type IN ({plans})
            AND s.payment_status = 'completed'
            AND (s.expires_at IS NULL OR s.expires_at > %s)
        """
    cursor.execute(mrr_query.format(plans="%s"), ["professional", now_ist])
    pro_mrr_raw = cursor.fetchone()[0] or 0

    cursor.execute(mrr_query.format(plans="%s, %s"), ["basic", "starter", now_ist])
    starter_mrr_raw = cursor.fetchone()[0] or 0

    return pro_mrr_raw, starter_mrr_raw


def fetch_month_revenue(cursor, month, year):
    """Return completed revenue (float) for subscriptions created in the given month and year."""
    cursor.execute(
        "SELECT SUM(registration_amount) FROM agent_subscriptions WHERE MONTH(created_at) = %s AND YEAR(created_at) = %s AND payment_status = 'completed'",
        [month, year],
    )
    return float(cursor.fetchone()[0] or 0)


def fetch_recent_subscriptions(cursor):
    """Return the 15 latest completed subscriptions with agent name, email and display name."""
    cursor.execute("""
            SELECT
                s.*,
                a.fullname,
                a.email,
                ap.display_name
            FROM agent_subscriptions s
            JOIN agents a ON s.agent_id = a.id
            LEFT JOIN agent_profiles ap ON a.id = ap.agent_id
            WHERE s.payment_status = 'completed'
            ORDER BY s.created_at DESC
            LIMIT 15
        """)
    cols = [col[0] for col in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]
