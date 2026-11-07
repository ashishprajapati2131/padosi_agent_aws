import logging
from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.contrib import messages
import json
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .dashboard import _get_admin_from_session
from apps.admin_panel.models.admin_activity_log import AdminActivityLog
from apps.distributors.models import SubDistributor
from apps.admin_panel.services.distributors_service import (
    create_distributor,
    reset_distributor_password,
    reset_subdistributor_password,
    set_distributor_status,
)

from apps.admin_panel.selectors.distributors import (
    fetch_distributor_detail,
    fetch_distributors,
    user_email_exists,
)

logger = logging.getLogger(__name__)


def distributor_list(request):
    """
    Phase 6B.1: Distributors List View
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    search = request.GET.get("search", "")
    status_filter = request.GET.get("status", "all")

    distributors = []
    try:
        distributors = fetch_distributors(search, status_filter)
    except Exception as e:
        logger.error(f"Error fetching distributors list: {e}")

    paginator = Paginator(distributors, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "search": search,
        "status_filter": status_filter,
    }

    return render(request, "admin/distributors/list.html", context)


def distributor_create(request):
    """
    Phase 6B.2: Distributors Create View
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    return render(request, "admin/distributors/create.html")


def distributor_store(request):
    """
    Phase 6B.2: Store Distributor
    """
    if request.method != "POST":
        return redirect("admin_distributors_create")

    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    fullname = request.POST.get("fullname", "").strip()
    email = request.POST.get("email", "").strip()
    password = request.POST.get("password", "")
    confirm_password = request.POST.get("confirm_password", "")

    errors = {}

    if not fullname:
        errors["fullname"] = "The fullname field is required."

    if not email:
        errors["email"] = "The email field is required."
    else:
        # Check uniqueness
        if user_email_exists(email):
            errors["email"] = "The email has already been taken."

    if not password:
        errors["password"] = "The password field is required."
    elif len(password) < 8:
        errors["password"] = "The password must be at least 8 characters."

    if password and password != confirm_password:
        errors["confirm_password"] = "The password confirmation does not match."

    if errors:
        for field, msg in errors.items():
            messages.error(request, msg)
        return render(
            request,
            "admin/distributors/create.html",
            {
                "old": {
                    "fullname": fullname,
                    "email": email,
                },
                "errors": errors,
            },
        )

    # Success: Save User
    # Keep the legacy bcrypt hashing format ($2y$) used by Laravel
    import bcrypt

    salt = bcrypt.gensalt()
    bcrypt_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    # Convert python's $2b$ prefix to Laravel's expected $2y$ prefix
    hashed_password = bcrypt_hash.replace("$2b$", "$2y$", 1)
    now = timezone.now()

    try:
        create_distributor(fullname, email, hashed_password, now)

        messages.success(request, "Distributor created successfully.")
        return redirect("admin_distributors")

    except Exception as e:
        logger.error(f"Error creating distributor: {e}")
        messages.error(request, "Database error occurred while creating distributor.")
        return render(
            request,
            "admin/distributors/create.html",
            {
                "old": {
                    "fullname": fullname,
                    "email": email,
                }
            },
        )


def distributor_detail(request, distributor_id):
    """
    Phase 6B.3: Distributor Detail View
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    distributor = None
    referral_code = None
    agents = []

    try:
        detail = fetch_distributor_detail(distributor_id)
        if detail is None:
            from django.http import Http404

            raise Http404("Distributor not found")
        distributor, referral_code, agents = detail
    except Exception as e:
        logger.error(f"Error fetching distributor details: {e}")
        from django.http import Http404

        raise Http404("Database error")

    # Pagination
    paginator = Paginator(agents, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Generate registration link
    registration_link = ""
    if referral_code:
        base_url = f"{request.scheme}://{request.get_host()}"
        registration_link = f"{base_url}/register?refCode={referral_code}"

    # Sub-distributors under this distributor (admin can reset their passwords too).
    sub_distributors = list(
        SubDistributor.objects.filter(distributor_id=distributor_id)
        .order_by("-created_at")
        .values("id", "fullname", "email", "mobile", "status", "created_at")
    )

    context = {
        "distributor": distributor,
        "referral_code": referral_code,
        "registration_link": registration_link,
        "page_obj": page_obj,
        "sub_distributors": sub_distributors,
    }

    return render(request, "admin/distributors/show.html", context)


def toggle_distributor_status(request):
    """
    Phase 6B.4: Toggle Distributor Status
    """
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "Invalid request method."}, status=405
        )

    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({"success": False, "message": "Unauthorized."}, status=401)

    try:
        data = json.loads(request.body)
        distributor_id = data.get("id")
        target_status = data.get("status")

        if not distributor_id or target_status not in ["active", "suspended"]:
            return JsonResponse(
                {"success": False, "message": "Invalid input data."}, status=400
            )

        if not set_distributor_status(distributor_id, target_status):
            return JsonResponse(
                {"success": False, "message": "Distributor not found."}, status=404
            )

        return JsonResponse(
            {
                "success": True,
                "message": "Distributor status updated successfully",
                "status": target_status,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."}, status=400
        )
    except Exception as e:
        logger.error(f"Error toggling distributor status: {e}")
        return JsonResponse(
            {"success": False, "message": "Database error occurred."}, status=500
        )


# ─── PASSWORD RESET (admin-controlled) ────────────────────────────────────────


def _validate_new_password(password, confirm):
    """Return an error string, or None if the pair is valid."""
    if not password or len(password) < 8:
        return "Password must be at least 8 characters."
    if password != confirm:
        return "Passwords do not match."
    return None


@require_POST
def distributor_reset_password(request):
    """Super-admin / distributors-permission: set a new password for a parent distributor.

    The distributor logs in against the `users` table (bcrypt), so that is the
    row we update. Never reveals anything about other account types.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    distributor_id = request.POST.get("distributor_id")
    password = request.POST.get("password", "")
    confirm = request.POST.get("confirm_password", "")

    err = _validate_new_password(password, confirm)
    if err:
        messages.error(request, err)
        return (
            redirect("admin_distributor_detail", distributor_id=distributor_id)
            if distributor_id
            else redirect("admin_distributors")
        )

    user = reset_distributor_password(distributor_id, password)
    if not user:
        messages.error(request, "Distributor not found.")
        return redirect("admin_distributors")

    AdminActivityLog.log(
        f"Reset distributor password for {user.email}",
        "User",
        user.id,
        request=request,
    )
    messages.success(
        request, f"Password reset for distributor '{user.fullname or user.email}'."
    )
    return redirect("admin_distributor_detail", distributor_id=user.id)


@require_POST
def subdistributor_reset_password(request):
    """Admin: set a new password for a sub-distributor (sub_distributors table)."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    sub_id = request.POST.get("sub_distributor_id")
    password = request.POST.get("password", "")
    confirm = request.POST.get("confirm_password", "")

    sub = SubDistributor.objects.filter(id=sub_id).first()
    if not sub:
        messages.error(request, "Sub-distributor not found.")
        return redirect("admin_distributors")

    err = _validate_new_password(password, confirm)
    if err:
        messages.error(request, err)
        return redirect("admin_distributor_detail", distributor_id=sub.distributor_id)

    reset_subdistributor_password(sub, password)

    AdminActivityLog.log(
        f"Reset sub-distributor password for {sub.email}",
        "SubDistributor",
        sub.id,
        request=request,
    )
    messages.success(
        request, f"Password reset for sub-distributor '{sub.fullname or sub.email}'."
    )
    return redirect("admin_distributor_detail", distributor_id=sub.distributor_id)
