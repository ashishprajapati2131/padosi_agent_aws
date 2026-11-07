import math
from django.shortcuts import render
from .dashboard import _get_admin_from_session
from ..services.users_service import update_user
from ..selectors.users import (
    count_users,
    email_taken_by_other_user,
    fetch_user_id_email,
    fetch_user_with_agent_id,
    fetch_users_page,
    user_list_filter,
)


def _build_user_list_query(request):
    """
    Builds the base query, arguments, and total count for users list.
    """
    search = request.GET.get("search", "").strip()
    role = request.GET.get("role", "").strip()
    status = request.GET.get("status", "").strip()

    base_query, args = user_list_filter(search, role, status)
    total = count_users(base_query, args)

    return base_query, args, total


def user_list(request):
    """
    Phase 6C.1: Users / Clients list page.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return render(request, "admin/login.html", {"error": "Please login first"})

    base_query, args, total = _build_user_list_query(request)

    # Pagination
    try:
        page = int(request.GET.get("page", 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    per_page = 15
    total_pages = math.ceil(total / per_page) if total > 0 else 1
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page

    users = fetch_users_page(base_query, args, per_page, offset)

    context = {
        "users": users,
        "search": request.GET.get("search", ""),
        "role": request.GET.get("role", ""),
        "status": request.GET.get("status", ""),
        "page": page,
        "total_pages": total_pages,
        "total_users": total,
        "page_range": range(1, total_pages + 1),
    }

    return render(request, "admin/users/list.html", context)


def user_edit(request, user_id):
    """
    Phase 6C.2: User edit page
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    user, agent_id = fetch_user_with_agent_id(user_id)
    if user is None:
        messages.error(request, "User not found")
        return redirect("admin_users")

    errors = request.session.pop("form_errors", {})
    old = request.session.pop("form_old", {})

    context = {"user": user, "agent_id": agent_id, "errors": errors, "old": old}

    return render(request, "admin/users/edit.html", context)


import re
from django.contrib import messages
from django.shortcuts import redirect


def user_update(request, user_id):
    """
    Phase 6C.2: User update logic
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    if request.method != "POST":
        return redirect("admin_users_edit", user_id=user_id)

    user_row = fetch_user_id_email(user_id)

    if not user_row:
        messages.error(request, "User not found")
        return redirect("admin_users")

    fullname = request.POST.get("fullname", "").strip()
    email = request.POST.get("email", "").strip()
    role = request.POST.get("role", "").strip()
    status = request.POST.get("status", "").strip()
    password = request.POST.get("password", "")
    password_confirmation = request.POST.get("password_confirmation", "")

    errors = {}

    if not fullname:
        errors["fullname"] = "The fullname field is required."
    elif len(fullname) > 255:
        errors["fullname"] = "The fullname must not be greater than 255 characters."

    if not email:
        errors["email"] = "The email field is required."
    elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        errors["email"] = "The email must be a valid email address."
    elif email_taken_by_other_user(email, user_id):
        errors["email"] = "The email has already been taken."

    if not role:
        errors["role"] = "The role field is required."
    elif role not in ["admin", "agent", "client"]:
        errors["role"] = "The selected role is invalid."

    if not status:
        errors["status"] = "The status field is required."
    elif status not in ["active", "inactive", "suspended"]:
        errors["status"] = "The selected status is invalid."

    if password:
        if len(password) < 8:
            errors["password"] = "The password must be at least 8 characters."
        elif password != password_confirmation:
            errors["password"] = "The password confirmation does not match."

    # Login credentials (password, email) of any user incl. distributors: Super Admin only.
    if password or email.lower() != (user_row[1] or "").lower():
        from apps.admin_panel.views.pages import _is_super_admin

        if not _is_super_admin(admin_id):
            errors["email" if not password else "password"] = (
                "Only a Super Admin can change a user's email or password."
            )

    if errors:
        request.session["form_errors"] = errors
        # Never keep plaintext passwords in the session store.
        request.session["form_old"] = {
            k: v
            for k, v in request.POST.dict().items()
            if k not in ("password", "password_confirmation", "csrfmiddlewaretoken")
        }
        return redirect("admin_users_edit", user_id=user_id)

    try:
        update_user(user_id, fullname, email, role, status, password)
        messages.success(request, "User updated successfully")
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Error updating user: {e}")
        messages.error(request, "Failed to update user due to a database error.")

    return redirect("admin_users")
