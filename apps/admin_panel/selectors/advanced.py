"""Read-only queries for the admin analytics and activity-log pages (views/advanced.py)."""

from django.db import connection


def fetch_top_agent_lead_rows(start_date):
    """Return up to 10 (agent_id, leads_count) rows for leads created since start_date."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT a.id, COUNT(l.id) as leads_count
                FROM agents a
                JOIN agent_leads l ON a.id = l.agent_id
                WHERE l.created_at >= %s
                GROUP BY a.id
                HAVING leads_count > 0
                ORDER BY leads_count DESC
                LIMIT 10
            """,
            [start_date],
        )
        return cursor.fetchall()


def fetch_top_agent_profile_view_rows(start_date):
    """Return up to 10 (agent_id, profile_views_count, avg_rating) rows for views since start_date."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT a.id, COUNT(v.id) as profile_views_count,
                       (SELECT COALESCE(AVG(rating), 0) FROM agent_reviews WHERE agent_id = a.id AND is_approved = 1) as avg_rating
                FROM agents a
                JOIN agent_profile_views v ON a.id = v.agent_id
                WHERE v.created_at >= %s
                GROUP BY a.id
                HAVING profile_views_count > 0
                ORDER BY profile_views_count DESC
                LIMIT 10
            """,
            [start_date],
        )
        return cursor.fetchall()


def fetch_overall_lead_and_view_counts(start_date):
    """Return (lead_count, profile_view_count) for rows created since start_date."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM agent_leads WHERE created_at >= %s", [start_date]
        )
        overall_leads = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM agent_profile_views WHERE created_at >= %s",
            [start_date],
        )
        overall_views = cursor.fetchone()[0]
    return overall_leads, overall_views


def fetch_daily_leads_last_30_days():
    """Return per-day lead dicts {'label', 'whatsapp', 'call'} for the last 30 days."""
    with connection.cursor() as cursor:
        cursor.execute("""
                SELECT
                    DATE_FORMAT(created_at, '%d %b') as label,
                    DATE(created_at) as date,
                    SUM(CASE WHEN interaction_type = 'whatsapp' THEN 1 ELSE 0 END) as whatsapp,
                    SUM(CASE WHEN interaction_type = 'call' THEN 1 ELSE 0 END) as `call`
                FROM agent_leads
                WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                GROUP BY DATE(created_at), label
                ORDER BY DATE(created_at) ASC
            """)
        rows = cursor.fetchall()
    return [
        {"label": r[0], "whatsapp": int(r[2] or 0), "call": int(r[3] or 0)}
        for r in rows
    ]


def fetch_admin_id_name_rows(admin_ids):
    """Return (id, name) rows from admins for the given non-empty collection of ids."""
    placeholders = ", ".join(["%s"] * len(admin_ids))
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT id, name FROM admins WHERE id IN ({placeholders})", list(admin_ids)
        )
        return cursor.fetchall()


def fetch_admin_name_row(admin_id):
    """Return the (name,) row for an admin id, or None when no admins row matches."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM admins WHERE id = %s", [admin_id])
        return cursor.fetchone()
