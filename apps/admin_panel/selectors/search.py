"""Read-only queries backing the admin global search (views/search.py)."""

from django.db import connection


def fetch_matching_agents(search_pattern):
    """Return up to 5 agents (id, fullname, email, mobile dicts) matching the LIKE pattern."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT id, fullname, email, mobile
                FROM agents
                WHERE fullname LIKE %s OR email LIKE %s OR mobile LIKE %s
                LIMIT 5
                """,
            [search_pattern, search_pattern, search_pattern],
        )
        return [
            {"id": agent_id, "fullname": fullname, "email": email, "mobile": mobile}
            for agent_id, fullname, email, mobile in cursor.fetchall()
        ]


def fetch_matching_users(search_pattern):
    """Return up to 3 users (id, fullname, email, mobile dicts) matching the LIKE pattern."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT id, fullname, email, mobile
                FROM users
                WHERE fullname LIKE %s OR email LIKE %s OR mobile LIKE %s
                LIMIT 3
                """,
            [search_pattern, search_pattern, search_pattern],
        )
        return [
            {"id": user_id, "fullname": fullname, "email": email, "mobile": mobile}
            for user_id, fullname, email, mobile in cursor.fetchall()
        ]


def fetch_matching_invoices(search_pattern):
    """Return up to 3 invoices (id, invoice_number, amount dicts) matching the LIKE pattern."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
                SELECT id, invoice_number, amount
                FROM invoices
                WHERE invoice_number LIKE %s
                LIMIT 3
                """,
            [search_pattern],
        )
        return [
            {"id": inv_id, "invoice_number": inv_num, "amount": amount}
            for inv_id, inv_num, amount in cursor.fetchall()
        ]
