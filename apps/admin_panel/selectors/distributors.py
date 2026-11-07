"""Read-only raw SQL for the admin distributors views."""

from django.db import connection


def _build_distributor_list_query(search, status_filter):
    """
    Builds the raw SQL query and params for the distributor list based on Laravel logic.
    """
    query = """
        SELECT
            u.id, u.fullname, u.email, u.status, u.created_at,
            (SELECT COUNT(*) FROM agents WHERE distributor_id = u.id) AS agents_count
        FROM users AS u
        WHERE u.role = 'distributor'
    """
    params = []

    if search:
        query += " AND (u.fullname LIKE %s OR u.email LIKE %s)"
        search_param = f"%{search}%"
        params.extend([search_param, search_param])

    if status_filter and status_filter != "all":
        query += " AND u.status = %s"
        params.append(status_filter)

    query += " ORDER BY u.created_at DESC"

    return query, params


def fetch_distributors(search, status_filter):
    """Return the filtered distributor rows (with agents_count) as a list of dicts."""
    query, params = _build_distributor_list_query(search, status_filter)
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def user_email_exists(email):
    """Return True if any users row already has this email."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE email = %s", [email])
        return bool(cursor.fetchone())


def fetch_distributor_detail(distributor_id):
    """Return (distributor dict, referral_code or None, agents list), or None if no such distributor."""
    query_distributor = """
        SELECT
            u.id, u.fullname, u.email, u.status, u.created_at,
            (SELECT COUNT(*) FROM agents WHERE distributor_id = u.id) AS agents_count
        FROM users AS u
        WHERE u.role = 'distributor' AND u.id = %s
    """

    referral_code = None
    query_referral = """
        SELECT code FROM referral_codes WHERE distributor_id = %s LIMIT 1
    """

    query_agents = """
        SELECT
            a.id, a.fullname, a.email, a.status, a.created_at,
            s.selected_plan
        FROM agents AS a
        LEFT JOIN agent_subscriptions AS s ON a.id = s.agent_id
            AND s.id = (SELECT MAX(id) FROM agent_subscriptions WHERE agent_id = a.id)
        WHERE a.distributor_id = %s
        ORDER BY a.created_at DESC
    """

    with connection.cursor() as cursor:
        # Fetch distributor
        cursor.execute(query_distributor, [distributor_id])
        row = cursor.fetchone()
        if not row:
            return None

        columns = [col[0] for col in cursor.description]
        distributor = dict(zip(columns, row))

        # Fetch referral code
        cursor.execute(query_referral, [distributor_id])
        ref_row = cursor.fetchone()
        if ref_row:
            referral_code = ref_row[0]

        # Fetch agents
        cursor.execute(query_agents, [distributor_id])
        agent_columns = [col[0] for col in cursor.description]
        agents = [dict(zip(agent_columns, r)) for r in cursor.fetchall()]

    return distributor, referral_code, agents
