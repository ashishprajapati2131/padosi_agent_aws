"""Write flows for administrator management (views/admins.py)."""

from password_hashing import hash_password

from apps.admin_panel.models.admin_auth import Admin


def create_admin(name, email, password, role, permissions_selected):
    hashed_password = hash_password(password)
    permissions = None if role == "super" else (permissions_selected or [])

    Admin.objects.create(
        name=name,
        email=email,
        password=hashed_password,
        role=role,
        permissions=permissions,
    )


def update_admin(
    admin, name, email, password, role, permissions_selected, current_session_token
):
    admin.name = name
    admin.email = email
    admin.role = role
    admin.permissions = None if role == "super" else (permissions_selected or [])

    if password:
        admin.password = hash_password(password)

    admin.save()

    if password:
        # A reset must end the old sessions (a stolen session stayed valid for 7 days).
        from apps.admin_panel.models.user_session import UserSession

        UserSession.objects.filter(admin_id=admin.id).exclude(
            session_token=current_session_token
        ).delete()


def delete_admin(admin):
    admin.delete()
