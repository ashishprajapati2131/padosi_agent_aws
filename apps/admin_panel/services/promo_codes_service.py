"""Promo code write flows used by apps/admin_panel/views/promo_codes.py.

Database errors propagate; the views turn them into user-facing messages.
"""

from django.db import connection


def toggle_promo_code_status(promo_id):
    """Flip is_active. Returns the new status (0/1), or None if the promo code does not exist."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT is_active FROM promo_codes WHERE id = %s", [promo_id])
        row = cursor.fetchone()
        if not row:
            return None

        current_status = row[0]
        new_status = 0 if current_status else 1

        cursor.execute(
            "UPDATE promo_codes SET is_active = %s, updated_at = NOW() WHERE id = %s",
            [new_status, promo_id],
        )
    return new_status


def create_promo_code(
    code, discount_type, discount_value, applicable_plan, max_uses, expires_at
):
    """Insert a promo code. Returns False (nothing written) if the code already exists."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM promo_codes WHERE UPPER(code) = %s", [code])
        if cursor.fetchone():
            return False

        cursor.execute(
            """
            INSERT INTO promo_codes (
                code, discount_type, discount_value, applicable_plan,
                max_uses, expires_at, is_active, times_used, is_free_trial, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 1, 0, 0, NOW(), NOW())
        """,
            [
                code,
                discount_type,
                discount_value,
                applicable_plan,
                max_uses,
                expires_at,
            ],
        )
    return True


def update_promo_code(
    promo_id, code, discount_type, discount_value, applicable_plan, max_uses, expires_at
):
    """Update a promo code. Returns False (nothing written) if another record already uses the code."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM promo_codes WHERE UPPER(code) = %s AND id != %s",
            [code, promo_id],
        )
        if cursor.fetchone():
            return False

        cursor.execute(
            """
            UPDATE promo_codes SET
                code = %s, discount_type = %s, discount_value = %s, applicable_plan = %s,
                max_uses = %s, expires_at = %s, updated_at = NOW()
            WHERE id = %s
        """,
            [
                code,
                discount_type,
                discount_value,
                applicable_plan,
                max_uses,
                expires_at,
                promo_id,
            ],
        )
    return True
