import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q, F, Sum
from django.core.paginator import Paginator

# Use session based authentication
from apps.admin_panel.views.dashboard import _get_admin_from_session

# Use Phase 3A models
from apps.admin_panel.models import AgentSubscription, AdminActivityLog
from apps.agents.models import PaymentStatus
from apps.admin_panel.services.subscriptions_service import delete_unpaid_subscription


def subscriptions_index(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    filter_val = request.GET.get("filter", "all")
    now = timezone.now()

    # Query active subscriptions for agents with active status
    # Only real (paid, current) rows: checkout attempts, failed and superseded rows were
    # listed and counted too, so one agent with 3 attempts counted 3 times.
    paid_active = AgentSubscription.objects.filter(
        agent__status="active", payment_status=PaymentStatus.COMPLETED, status="active"
    )
    query = paid_active.select_related("agent", "agent__profile")

    if filter_val == "expired":
        query = query.filter(expires_at__lt=now)
    elif filter_val == "expiring_soon":
        query = query.filter(
            expires_at__gte=now, expires_at__lte=now + timezone.timedelta(days=30)
        )

    # Order by: NULL expires_at should be last, others ascending by expires_at.
    subscriptions_qs = query.order_by(F("expires_at").asc(nulls_last=True))

    page_number = request.GET.get("page", 1)
    paginator = Paginator(subscriptions_qs, 25)
    page_obj = paginator.get_page(page_number)

    # Precalculate dynamic attributes for each subscription
    for sub in page_obj:
        if sub.expires_at:
            diff = sub.expires_at - now
            days_left = int(diff.total_seconds() / 86400)
            sub.days_left = days_left
            sub.days_left_abs = abs(days_left)
            sub.is_expiring_soon = not sub.is_expired and days_left <= 30
        else:
            sub.days_left = None
            sub.is_expiring_soon = False

        # Status badge attributes
        if sub.is_expired:
            sub.badge_class = "bg-danger"
            sub.badge_text = "Expired"
        elif sub.is_expiring_soon:
            sub.badge_class = "bg-warning text-dark"
            sub.badge_text = "Expiring Soon"
        else:
            sub.badge_class = "bg-success"
            sub.badge_text = "Active"

        agent = sub.agent
        sub.display_fullname = agent.fullname
        sub.display_email = agent.email
        try:
            profile = agent.profile
            sub.display_name = profile.display_name or agent.fullname
        except Exception:
            sub.display_name = agent.fullname

    # Stats for summary cards
    active_subs = paid_active

    expired_count = active_subs.filter(expires_at__lt=now).count()

    expiring_30_count = active_subs.filter(
        expires_at__gte=now, expires_at__lte=now + timezone.timedelta(days=30)
    ).count()

    expiring_60_count = active_subs.filter(
        expires_at__gt=now + timezone.timedelta(days=30),
        expires_at__lte=now + timezone.timedelta(days=60),
    ).count()

    active_healthy_count = active_subs.filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now + timezone.timedelta(days=60))
    ).count()

    # Estimated monthly revenue = what current subscribers actually paid (yearly plans) / 12.
    # Was hard-coded 999/499 per agent, unrelated to real prices.
    paid_total = (
        active_subs.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).aggregate(total=Sum("registration_amount"))["total"]
        or 0
    )
    est_revenue = int(round(float(paid_total) / 12))

    stats = {
        "expired": expired_count,
        "expiring_30": expiring_30_count,
        "expiring_60": expiring_60_count,
        "active_healthy": active_healthy_count,
        "est_revenue": est_revenue,
    }

    context = {
        "subscriptions": page_obj.object_list,
        "page_obj": page_obj,
        "stats": stats,
        "filter": filter_val,
    }

    return render(request, "admin/subscriptions.html", context)


def delete_subscription(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=401)

    if request.method == "POST":
        sub_id = request.POST.get("id")

        # Support JSON payload
        if not sub_id and request.content_type == "application/json":
            try:
                data = json.loads(request.body)
                sub_id = data.get("id")
            except Exception:
                pass

        if not sub_id:
            return JsonResponse(
                {"success": False, "message": "Subscription ID is required"}, status=400
            )

        subscription = get_object_or_404(AgentSubscription, id=sub_id)
        if not delete_unpaid_subscription(subscription):
            return JsonResponse(
                {"success": False, "message": "Paid subscriptions cannot be deleted."},
                status=400,
            )

        # Log admin activity
        AdminActivityLog.log(
            "Delete subscription", "AgentSubscription", sub_id, request=request
        )

        return JsonResponse(
            {"success": True, "message": "Subscription deleted successfully"}
        )

    return JsonResponse(
        {"success": False, "message": "Invalid request method"}, status=405
    )
