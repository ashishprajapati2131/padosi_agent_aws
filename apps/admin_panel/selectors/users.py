"""Read-only queries for the admin users pages (views/users.py)."""

from django.db import connection


def user_list_filter(search, role, status):
    """Return (base_query, args) for the user list filters."""
    # Base query matches Laravel User::query() which does SELECT * FROM users
    base_query = "FROM users WHERE 1=1"
    args = []

    if search:
        # Match Laravel: where(function($q) use ($search) { $q->where('fullname', 'LIKE', "%{$search}%")->orWhere('email', 'LIKE', "%{$search}%"); })
        base_query += " AND (fullname LIKE %s OR email LIKE %s)"
        search_term = f"%{search}%"
        args.extend([search_term, search_term])

    if role and role != "all":
        base_query += " AND role = %s"
        args.append(role)

    if status and status != "all":
        base_query += " AND status = %s"
        args.append(status)

    return base_query, args


def count_users(base_query, args):
    """Return the number of users matching base_query/args."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(id) {base_query}", args)
        total_row = cursor.fetchone()
        return total_row[0] if total_row else 0


def fetch_users_page(base_query, args, per_page, offset):
    """Return one page of user dicts, newest first."""
    # Ordering matching Laravel: orderBy('created_at', 'desc')
    query = f"SELECT * {base_query} ORDER BY created_at DESC LIMIT %s OFFSET %s"

    with connection.cursor() as cursor:
        cursor.execute(query, args + [per_page, offset])
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def fetch_user_with_agent_id(user_id):
    """Return (user dict, agent_id) for user_id, or (None, 0) if no such user."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM users WHERE id = %s", [user_id])
        row = cursor.fetchone()
        if not row:
            return None, 0

        columns = [col[0] for col in cursor.description]
        user = dict(zip(columns, row))

        agent_id = 0
        if user["role"] == "agent":
            cursor.execute("SELECT id FROM agents WHERE user_id = %s", [user_id])
            agent_row = cursor.fetchone()
            if agent_row:
                agent_id = agent_row[0]

    return user, agent_id


def fetch_user_id_email(user_id):
    """Return the (id, email) row for user_id, or None."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, email FROM users WHERE id = %s", [user_id])
        return cursor.fetchone()


def email_taken_by_other_user(email, user_id):
    """Return True if another user already has this email."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM users WHERE email = %s AND id != %s", [email, user_id]
        )
        return bool(cursor.fetchone())
