"""Write flows for the admin users module (views/users.py)."""

from django.db import connection
from password_hashing import hash_password


def update_user(user_id, fullname, email, role, status, password):
    """UPDATE users with already-validated values; a non-empty password is hashed here."""
    update_fields = ["fullname = %s", "email = %s", "role = %s", "status = %s"]
    update_args = [fullname, email, role, status]

    if password:
        update_fields.append("password = %s")
        hashed_password = hash_password(password)
        update_args.append(hashed_password)

    update_args.append(user_id)
    query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = %s"

    with connection.cursor() as cursor:
        cursor.execute(query, update_args)
