"""Read-only raw SQL for the admin agent pages (views/agents.py).

Callers keep their own try/except + logging; these functions let errors propagate.
"""

from django.db import connection


def _dict_rows(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_agent_list_count(body, params):
    """Return the total row count for an agent-list query body (FROM ... WHERE ...)."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) " + body, params)
        return int(cursor.fetchone()[0] or 0)


def fetch_agent_list_page(query, params, limit, offset):
    """Return one page of agent-list rows as dicts."""
    with connection.cursor() as cursor:
        cursor.execute(
            query + " LIMIT %s OFFSET %s",
            params + [limit, offset],
        )
        return _dict_rows(cursor)


def fetch_agent_detail(agent_id):
    """Return the manage-page agent row as a dict, or None if not found."""
    query = """
        SELECT
            a.id, a.fullname, a.email, a.mobile, a.status, a.admin_restricted, a.plan_type, a.created_at, a.experience_range, a.admin_notes, a.achievement_photo_limit,
            ap.address, ap.license_number, ap.experience_years, ap.office_address, ap.pan_number, ap.profile_photo_path,
            ap.is_profile_visible, ap.is_card_visible, ap.show_certificates, ap.show_achievements, ap.show_reviews,
            ap.show_experience, ap.show_claims_stats, ap.show_client_base, ap.show_ratings,
            ap.show_languages, ap.show_gallery, ap.show_contact_info, ap.show_social_links,
            ap.license_valid_till, ap.arn_number, ap.euin_number, ap.investment_valid_till, ap.investment_types,
            s.selected_plan, s.expires_at,
            (SELECT AVG(rating) FROM agent_reviews WHERE agent_id = a.id AND is_approved = 1) as avg_rating,
            (SELECT COUNT(*) FROM agent_reviews WHERE agent_id = a.id AND is_approved = 1) as review_count,
            (SELECT COUNT(*) FROM agent_reviews WHERE agent_id = a.id AND is_approved = 0) as pending_reviews
        FROM agents AS a
        LEFT JOIN agent_profiles AS ap ON a.id = ap.agent_id
        LEFT JOIN agent_subscriptions AS s ON a.id = s.agent_id
            AND s.id = (SELECT MAX(id) FROM agent_subscriptions WHERE agent_id = a.id)
        WHERE a.id = %s
    """
    with connection.cursor() as cursor:
        cursor.execute(query, [agent_id])
        row = cursor.fetchone()
        if row:
            columns = [col[0] for col in cursor.description]
            return dict(zip(columns, row))
    return None


def fetch_agent_recent_reviews(agent_id):
    """Return the agent's 10 newest reviews as dicts."""
    reviews_query = """
        SELECT
            r.id, r.rating, r.review as review_text, r.is_approved, r.created_at,
            u.fullname as client_name
        FROM agent_reviews AS r
        LEFT JOIN users AS u ON r.user_id = u.id
        WHERE r.agent_id = %s
        ORDER BY r.created_at DESC
        LIMIT 10
    """
    with connection.cursor() as cursor:
        cursor.execute(reviews_query, [agent_id])
        return _dict_rows(cursor)


def fetch_agent_json(agent_id):
    """Return the quick-view agent row as a dict, or None if not found."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT
                    a.id, a.fullname, a.email, a.mobile as phone, a.status, ap.address as location,
                    ap.license_number as license, ap.experience_years as experience, a.admin_notes,
                    s.selected_plan
                FROM agents AS a
                LEFT JOIN agent_profiles AS ap ON a.id = ap.agent_id
                LEFT JOIN agent_subscriptions AS s ON a.id = s.agent_id
                    AND s.id = (SELECT MAX(id) FROM agent_subscriptions WHERE agent_id = a.id)
                WHERE a.id = %s
            """,
            [agent_id],
        )

        row = cursor.fetchone()
        if row:
            columns = [col[0] for col in cursor.description]
            return dict(zip(columns, row))
    return None


def fetch_event_names():
    """Return all events as [{'id', 'name'}] ordered by name."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, name FROM events ORDER BY name ASC")
        return _dict_rows(cursor)


def fetch_queue_rows(query, params):
    """Return the rows of a _build_queue_query() query as dicts."""
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return _dict_rows(cursor)


def count_missing_irdai_agents():
    """Return how many active agents have no IRDAI license number."""
    with connection.cursor() as cursor:
        # Grows with every unlicensed active agent; show the newest and the real total.
        cursor.execute(
            """SELECT COUNT(*) FROM agents AS a LEFT JOIN agent_profiles AS ap ON a.id = ap.agent_id
                   WHERE a.status = 'active' AND (ap.license_number IS NULL OR ap.license_number = '')"""
        )
        return cursor.fetchone()[0]


def fetch_missing_irdai_agents(limit):
    """Return the newest `limit` active agents with no IRDAI license as dicts."""
    missing_query = """
            SELECT a.id, a.fullname, a.email, a.mobile, a.badge, ap.pan_number, ap.license_number
            FROM agents as a
            LEFT JOIN agent_profiles as ap ON a.id = ap.agent_id
            WHERE a.status = 'active'
              AND (ap.license_number IS NULL OR ap.license_number = '')
            ORDER BY a.id DESC
            LIMIT %s
        """
    with connection.cursor() as cursor:
        cursor.execute(missing_query, [limit])
        return _dict_rows(cursor)


def fetch_pending_drafts(search, city_filter, sort_by):
    """Return raw agent_drafts rows (step >= 1, email not yet an agent) as dicts."""
    _draft_hours_expr = (
        "CAST((julianday('now') - julianday(d.created_at)) * 24 AS INTEGER)"
        if connection.vendor == "sqlite"
        else "TIMESTAMPDIFF(HOUR, d.created_at, NOW())"
    )
    draft_query = f"""
                SELECT
                    d.id, d.fullname, d.email, d.mobile,
                    d.address, d.state, d.agent_pincode,
                    d.registration_step, d.created_at, d.updated_at,
                    {_draft_hours_expr} AS hours_waiting
                FROM agent_drafts AS d
                WHERE d.registration_step >= 1
                  AND d.email NOT IN (SELECT email FROM agents WHERE email IS NOT NULL AND email != '')
            """
    draft_params = []
    if search:
        draft_query += " AND (d.fullname LIKE %s OR d.email LIKE %s)"
        sp = f"%{search}%"
        draft_params.extend([sp, sp])
    if city_filter:
        draft_query += " AND (d.address LIKE %s OR d.state LIKE %s)"
        cp = f"%{city_filter}%"
        draft_params.extend([cp, cp])
    if sort_by == "oldest":
        draft_query += " ORDER BY d.created_at ASC"
    elif sort_by == "waiting":
        draft_query += f" ORDER BY {_draft_hours_expr} DESC"
    else:
        draft_query += " ORDER BY d.created_at DESC"
    with connection.cursor() as _cur:
        _cur.execute(draft_query, draft_params)
        return _dict_rows(_cur)


def fetch_latest_draft_events(draft_ids):
    """Return {draft_id (str): latest registration_activity_logs event_name}."""
    event_map = {}
    with connection.cursor() as _cur:
        placeholders = ",".join(["%s"] * len(draft_ids))
        _cur.execute(
            f"SELECT draft_id, event_name FROM registration_activity_logs "
            f"WHERE draft_id IN ({placeholders}) ORDER BY created_at DESC",
            draft_ids,
        )
        for row in _cur.fetchall():
            did, ev = str(row[0]), row[1]
            if did not in event_map:
                event_map[did] = ev
    return event_map


def fetch_latest_agent_events(agent_ids):
    """Return {agent_id (str): latest registration_activity_logs event_name}."""
    event_map = {}
    with connection.cursor() as _cur:
        placeholders = ",".join(["%s"] * len(agent_ids))
        _cur.execute(
            f"SELECT agent_id, event_name FROM registration_activity_logs "
            f"WHERE agent_id IN ({placeholders}) ORDER BY created_at DESC",
            agent_ids,
        )
        for row in _cur.fetchall():
            aid, ev = str(row[0]), row[1]
            if aid not in event_map:
                event_map[aid] = ev
    return event_map
