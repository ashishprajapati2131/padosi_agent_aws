import json
import logging
from django.shortcuts import render, redirect
from django.http import JsonResponse, Http404
from django.db import connection
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect

from .dashboard import _get_admin_from_session

logger = logging.getLogger(__name__)

@require_http_methods(["GET"])
def promo_code_list(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

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

    context = {
        'admin': admin,
        'promo_codes': promo_codes,
    }

    return render(request, "admin/promo_codes/index.html", context)

@csrf_protect
@require_http_methods(["POST"])
def toggle_promo_code_status(request, promo_id):
    admin = _get_admin_from_session(request)
    if not admin:
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=401)

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT is_active FROM promo_codes WHERE id = %s", [promo_id])
            row = cursor.fetchone()
            if not row:
                return JsonResponse({"success": False, "message": "Promo code not found."}, status=404)

            current_status = row[0]
            new_status = 0 if current_status else 1

            cursor.execute("UPDATE promo_codes SET is_active = %s, updated_at = NOW() WHERE id = %s", [new_status, promo_id])
            
        return JsonResponse({
            "success": True,
            "is_active": bool(new_status),
            "message": "Status updated successfully."
        })
    except Exception as exc:
        logger.error("Error toggling promo code status for id %s: %s", promo_id, exc, exc_info=True)
        return JsonResponse({"success": False, "message": f"Database error: {str(exc)}"}, status=500)

@csrf_protect
@require_http_methods(["POST"])
def store_promo_code(request):
    from django.contrib import messages
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    code = request.POST.get("code", "").strip().upper()
    discount_type = request.POST.get("discount_type", "").strip()
    discount_value_raw = request.POST.get("discount_value", "").strip()
    applicable_plan_raw = request.POST.get("applicable_plan", "").strip()
    max_uses_raw = request.POST.get("max_uses", "").strip()
    expires_at_raw = request.POST.get("expires_at", "").strip()

    if not code:
        messages.error(request, "Promo code is required.")
        return redirect("admin_promo_codes")

    if discount_type not in ["percentage", "fixed"]:
        messages.error(request, "Please select a valid discount type.")
        return redirect("admin_promo_codes")

    try:
        discount_value = float(discount_value_raw)
        if discount_value <= 0:
            messages.error(request, "Discount value must be greater than zero.")
            return redirect("admin_promo_codes")
        if discount_type == "percentage" and discount_value > 100:
            messages.error(request, "Percentage discount cannot exceed 100%.")
            return redirect("admin_promo_codes")
    except (ValueError, TypeError):
        messages.error(request, "Please enter a valid numeric discount value.")
        return redirect("admin_promo_codes")

    if not applicable_plan_raw or applicable_plan_raw in ("all", "None"):
        applicable_plan = None
    elif applicable_plan_raw in ("basic", "starter"):
        applicable_plan = "basic"
    elif applicable_plan_raw == "professional":
        applicable_plan = "professional"
    else:
        messages.error(request, "Invalid applicable plan selected.")
        return redirect("admin_promo_codes")

    max_uses = None
    if max_uses_raw:
        try:
            m = int(max_uses_raw)
            if m > 0:
                max_uses = m
        except (ValueError, TypeError):
            max_uses = None

    expires_at = None
    if expires_at_raw:
        if len(expires_at_raw) == 10:
            expires_at = f"{expires_at_raw} 23:59:59"
        else:
            expires_at = expires_at_raw

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM promo_codes WHERE UPPER(code) = %s", [code])
            if cursor.fetchone():
                messages.error(request, f"The promo code '{code}' already exists.")
                return redirect("admin_promo_codes")

            cursor.execute("""
                INSERT INTO promo_codes (
                    code, discount_type, discount_value, applicable_plan, 
                    max_uses, expires_at, is_active, times_used, is_free_trial, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, 1, 0, 0, NOW(), NOW())
            """, [code, discount_type, discount_value, applicable_plan, max_uses, expires_at])

        messages.success(request, f"Promo Code '{code}' created successfully.")
    except Exception as exc:
        logger.error("Failed to store promo code %s: %s", code, exc, exc_info=True)
        messages.error(request, f"Database error creating promo code: {str(exc)}")

    return redirect("admin_promo_codes")

@csrf_protect
@require_http_methods(["POST"])
def update_promo_code(request, promo_id):
    from django.contrib import messages
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    code = request.POST.get("code", "").strip().upper()
    discount_type = request.POST.get("discount_type", "").strip()
    discount_value_raw = request.POST.get("discount_value", "").strip()
    applicable_plan_raw = request.POST.get("applicable_plan", "").strip()
    max_uses_raw = request.POST.get("max_uses", "").strip()
    expires_at_raw = request.POST.get("expires_at", "").strip()

    if not code:
        messages.error(request, "Promo code is required.")
        return redirect("admin_promo_codes")

    if discount_type not in ["percentage", "fixed"]:
        messages.error(request, "Please select a valid discount type.")
        return redirect("admin_promo_codes")

    try:
        discount_value = float(discount_value_raw)
        if discount_value <= 0:
            messages.error(request, "Discount value must be greater than zero.")
            return redirect("admin_promo_codes")
        if discount_type == "percentage" and discount_value > 100:
            messages.error(request, "Percentage discount cannot exceed 100%.")
            return redirect("admin_promo_codes")
    except (ValueError, TypeError):
        messages.error(request, "Please enter a valid numeric discount value.")
        return redirect("admin_promo_codes")

    if not applicable_plan_raw or applicable_plan_raw in ("all", "None"):
        applicable_plan = None
    elif applicable_plan_raw in ("basic", "starter"):
        applicable_plan = "basic"
    elif applicable_plan_raw == "professional":
        applicable_plan = "professional"
    else:
        messages.error(request, "Invalid applicable plan selected.")
        return redirect("admin_promo_codes")

    max_uses = None
    if max_uses_raw:
        try:
            m = int(max_uses_raw)
            if m > 0:
                max_uses = m
        except (ValueError, TypeError):
            max_uses = None

    expires_at = None
    if expires_at_raw:
        if len(expires_at_raw) == 10:
            expires_at = f"{expires_at_raw} 23:59:59"
        else:
            expires_at = expires_at_raw

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM promo_codes WHERE UPPER(code) = %s AND id != %s", [code, promo_id])
            if cursor.fetchone():
                messages.error(request, f"The promo code '{code}' already exists for another record.")
                return redirect("admin_promo_codes")

            cursor.execute("""
                UPDATE promo_codes SET
                    code = %s, discount_type = %s, discount_value = %s, applicable_plan = %s,
                    max_uses = %s, expires_at = %s, updated_at = NOW()
                WHERE id = %s
            """, [code, discount_type, discount_value, applicable_plan, max_uses, expires_at, promo_id])

        messages.success(request, f"Promo Code '{code}' updated successfully.")
    except Exception as exc:
        logger.error("Failed to update promo code %s: %s", promo_id, exc, exc_info=True)
        messages.error(request, f"Database error updating promo code: {str(exc)}")

    return redirect("admin_promo_codes")
