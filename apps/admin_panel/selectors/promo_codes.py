"""Read-only queries for the admin promo codes views."""

from django.db import connection


def fetch_promo_codes():
    """Return all promo codes as dicts, newest first."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, code, discount_type, discount_value, applicable_plan,
                   times_used, max_uses, expires_at, is_active
            FROM promo_codes
            ORDER BY id DESC
        """)

        columns = [col[0] for col in cursor.description]
        promo_codes = []
        for row in cursor.fetchall():
            promo = dict(zip(columns, row))
            promo_codes.append(promo)
    return promo_codes
