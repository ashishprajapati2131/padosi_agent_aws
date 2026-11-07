"""Read-only queries for the admin leads list (views/leads.py)."""

from django.db import connection


def _lead_where(search, type_filter, status_filter, date_from, date_to):
    """Return (where_sql, params) for the lead list filters."""
    where_clauses = []
    params = []

    if search:
        where_clauses.append(
            "(l.customer_name LIKE %s OR l.customer_email LIKE %s OR l.customer_mobile LIKE %s OR a.fullname LIKE %s)"
        )
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term, search_term])

    if type_filter != "all":
        where_clauses.append("l.interaction_type = %s")
        params.append(type_filter)

    if status_filter != "all":
        where_clauses.append("l.lead_status = %s")
        params.append(status_filter)

    if date_from:
        where_clauses.append("DATE(l.created_at) >= %s")
        params.append(date_from)

    if date_to:
        where_clauses.append("DATE(l.created_at) <= %s")
        params.append(date_to)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)
    return where_sql, params


def fetch_lead_stats():
    """Return the lead stat counters: total, today, whatsapp, call, new."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM agent_leads")
        total = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM agent_leads WHERE DATE(created_at) = CURDATE()"
        )
        today = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM agent_leads WHERE interaction_type = 'whatsapp'"
        )
        whatsapp = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM agent_leads WHERE interaction_type = 'call'"
        )
        call_leads = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM agent_leads WHERE lead_status = 'new'")
        new_leads = cursor.fetchone()[0]

    return {
        "total": total,
        "today": today,
        "whatsapp": whatsapp,
        "call": call_leads,
        "new": new_leads,
    }


def count_filtered_leads(search, type_filter, status_filter, date_from, date_to):
    """Return the number of leads matching the filters."""
    where_sql, params = _lead_where(
        search, type_filter, status_filter, date_from, date_to
    )
    count_query = f"""
            SELECT COUNT(*)
            FROM agent_leads l
            LEFT JOIN agents a ON l.agent_id = a.id
            LEFT JOIN agent_profiles ap ON a.id = ap.agent_id
            {where_sql}
        """
    with connection.cursor() as cursor:
        cursor.execute(count_query, params)
        return cursor.fetchone()[0]


def fetch_leads_page(
    search, type_filter, status_filter, date_from, date_to, per_page, offset
):
    """Return one page of filtered leads as dicts, newest first, with agent info."""
    where_sql, params = _lead_where(
        search, type_filter, status_filter, date_from, date_to
    )
    query = f"""
            SELECT
                l.*,
                a.fullname as agent_name,
                a.mobile as agent_mobile,
                ap.display_name as agent_display_name
            FROM agent_leads l
            LEFT JOIN agents a ON l.agent_id = a.id
            LEFT JOIN agent_profiles ap ON a.id = ap.agent_id
            {where_sql}
            ORDER BY l.created_at DESC
            LIMIT %s OFFSET %s
        """
    with connection.cursor() as cursor:
        cursor.execute(query, params + [per_page, offset])
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
