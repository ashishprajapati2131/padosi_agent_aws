"""Read-only queries for the admin Export Center (views/export.py)."""

from django.db import connection


ALLOWED_EXPORT_TABLES = {
    "agent_leads",
    "agents",
    "contact_submissions",
    "agent_subscriptions",
    "agent_reviews",
    "promo_codes",
    "pincodes",
    "insurance_companies",
    "referral_codes",
    "referral_usages",
    "free_trial_history",
}


def count_table(table: str) -> int:
    """Count rows in a raw table that may not have a Django model."""
    if table not in ALLOWED_EXPORT_TABLES:
        return 0
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
        return cursor.fetchone()[0]


def fetch_agent_export_rows(status_filter):
    """Return raw agent rows (profile + latest subscription) for the agents CSV."""
    with connection.cursor() as cursor:
        base_sql = """
            SELECT
                a.id, a.fullname, ap.display_name, a.email, a.mobile, a.status,
                ap.agency_name, ap.address, a.user_types, a.experience_range,
                s.selected_plan, s.expires_at, a.created_at
            FROM agents a
            LEFT JOIN agent_profiles ap ON a.id = ap.agent_id
            LEFT JOIN agent_subscriptions s ON a.id = s.agent_id
                AND s.id = (SELECT MAX(id) FROM agent_subscriptions WHERE agent_id = a.id)
        """
        params = []
        if status_filter != "all":
            base_sql += " WHERE a.status = %s"
            params.append(status_filter)
        base_sql += " ORDER BY a.created_at DESC"
        cursor.execute(base_sql, params)
        return cursor.fetchall()


def fetch_lead_export_rows(type_filter):
    """Return raw agent lead rows for the leads CSV."""
    with connection.cursor() as cursor:
        base_sql = """
            SELECT
                l.id, a.fullname, a.email,
                l.interaction_type,
                l.customer_name, l.customer_mobile,
                l.customer_email, l.customer_pincode,
                l.service_type, l.insurance_type,
                l.lead_status, l.created_at
            FROM agent_leads l
            LEFT JOIN agents a ON l.agent_id = a.id
        """
        params = []
        if type_filter != "all":
            base_sql += " WHERE l.interaction_type = %s"
            params.append(type_filter)
        base_sql += " ORDER BY l.created_at DESC"
        cursor.execute(base_sql, params)
        return cursor.fetchall()


def fetch_subscription_export_rows():
    """Return raw subscription history rows for the subscriptions CSV."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                s.id, a.fullname, a.email,
                s.selected_plan, s.registration_amount, s.payment_status,
                s.starts_at, s.expires_at, s.created_at
            FROM agent_subscriptions s
            JOIN agents a ON s.agent_id = a.id
            ORDER BY s.created_at DESC
        """)
        return cursor.fetchall()


def fetch_review_export_rows():
    """Return raw agent review rows for the reviews CSV."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                r.id, a.fullname AS agent_name,
                r.reviewer_name, r.rating, r.review,
                r.is_approved, r.created_at
            FROM agent_reviews r
            LEFT JOIN agents a ON r.agent_id = a.id
            ORDER BY r.created_at DESC
        """)
        return cursor.fetchall()


def fetch_pending_export_rows(search, event_sql, event_params):
    """Return raw incomplete/pending agent rows for the pending registrations CSV."""
    with connection.cursor() as cursor:
        base_sql = """
            SELECT
                a.id, a.fullname, ap.display_name, a.email, a.mobile,
                a.status, a.registration_step,
                s.selected_plan, s.registration_amount, s.payment_status,
                ap.address,
                TIMESTAMPDIFF(HOUR, a.created_at, UTC_TIMESTAMP()) AS hours_waiting,
                a.created_at
            FROM agents a
            LEFT JOIN agent_profiles ap ON a.id = ap.agent_id
            LEFT JOIN agent_subscriptions s ON a.id = s.agent_id
                AND s.id = (SELECT MAX(id) FROM agent_subscriptions WHERE agent_id = a.id)
            WHERE a.status IN ('incomplete', 'pending_payment', 'event_challenge')
        """
        params = []

        if search:
            base_sql += " AND (a.fullname LIKE %s OR a.email LIKE %s OR ap.display_name LIKE %s)"
            search_param = f"%{search}%"
            params.extend([search_param, search_param, search_param])

        base_sql += event_sql
        params.extend(event_params)

        base_sql += " ORDER BY TIMESTAMPDIFF(HOUR, a.created_at, UTC_TIMESTAMP()) DESC"

        cursor.execute(base_sql, params)
        return cursor.fetchall()
