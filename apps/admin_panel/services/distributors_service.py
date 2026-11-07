"""Write flows for the admin Distributors module (views/distributors.py)."""

import random
import re
import string

from django.db import connection, transaction

from password_hashing import hash_password
from apps.admin_panel.models import User as LaravelUser


def _generate_referral_code(fullname):
    # Take first 4 alphanumeric characters from fullname
    base = re.sub(r"[^A-Z0-9]", "", str(fullname).upper())[:4]

    # If less than 2 characters use prefix DIST
    if len(base) < 2:
        base = "DIST"

    # Append 4 random uppercase alphanumeric characters
    # Retry if code already exists
    while True:
        random_chars = "".join(
            random.choices(string.ascii_uppercase + string.digits, k=4)
        )
        code = f"{base}{random_chars}"

        # Check if exists
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM referral_codes WHERE code = %s", [code])
            if not cursor.fetchone():
                return code


def create_distributor(fullname, email, hashed_password, now):
    """Insert the distributor user and its referral code. Returns the new users.id."""
    # One transaction: a referral-code failure used to leave an orphan user ("email taken" on retry).
    with transaction.atomic(), connection.cursor() as cursor:
        # Insert User
        cursor.execute(
            """
            INSERT INTO users (fullname, email, password, role, status, created_at, updated_at)
            VALUES (%s, %s, %s, 'distributor', 'active', %s, %s)
        """,
            [fullname, email, hashed_password, now, now],
        )

        distributor_id = cursor.lastrowid

        # Generate and Insert Referral Code
        ref_code = _generate_referral_code(fullname)
        cursor.execute(
            """
            INSERT INTO referral_codes (distributor_id, code, is_active, created_at, updated_at, clicks, total_referrals, pending_referrals, reward_claimed)
            VALUES (%s, %s, 1, %s, %s, 0, 0, 0, 0)
        """,
            [distributor_id, ref_code, now, now],
        )
    return distributor_id


def set_distributor_status(distributor_id, target_status):
    """Update a distributor's status. Returns False if no such distributor."""
    with connection.cursor() as cursor:
        # Check if user exists and is a distributor
        cursor.execute(
            "SELECT id FROM users WHERE id = %s AND role = 'distributor'",
            [distributor_id],
        )
        if not cursor.fetchone():
            return False

        # Update status
        cursor.execute(
            "UPDATE users SET status = %s WHERE id = %s AND role = 'distributor'",
            [target_status, distributor_id],
        )
    return True


def reset_distributor_password(distributor_id, password):
    """Set a new password on a parent distributor. Returns the user, or None if not found."""
    user = LaravelUser.objects.filter(id=distributor_id, role="distributor").first()
    if not user:
        return None

    user.password = hash_password(password)
    try:
        user.save(update_fields=["password", "updated_at"])
    except Exception:
        user.save(update_fields=["password"])
    return user


def reset_subdistributor_password(sub, password):
    """Set a new password on a SubDistributor instance."""
    sub.password = hash_password(password)
    sub.save(update_fields=["password", "updated_at"])
