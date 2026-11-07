from apps.agents.models import PaymentStatus
import logging
from django.utils import timezone
from django.db import connection
from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.core.cache import cache
import json

from .dashboard import _get_admin_from_session
from ..services import agents_service
from ..selectors.agents import (
    count_missing_irdai_agents,
    fetch_agent_detail,
    fetch_agent_json,
    fetch_agent_list_count,
    fetch_agent_list_page,
    fetch_agent_recent_reviews,
    fetch_event_names,
    fetch_latest_agent_events,
    fetch_latest_draft_events,
    fetch_missing_irdai_agents,
    fetch_pending_drafts,
    fetch_queue_rows,
)
from apps.agents.services.feature_unlock import (
    PLAN_LABELS,
    paid_plan_label,
    plan_slug_from_name,
    resolve_agent_display_plan_label,
)

logger = logging.getLogger(__name__)


def _build_agent_list_query(
    search, plan_filter, status_filter, city_filter, promo_code_filter
):
    """
    Builds the raw SQL query and params for the agent list based on Laravel logic.
    """
    query = """
        SELECT
            a.id, a.fullname, a.email, a.mobile, a.status, a.plan_type, a.created_at, a.badge, a.is_blacklisted,
            ap.address, ap.state, ap.display_name,
            s.selected_plan, s.expires_at,
            (SELECT AVG(rating) FROM agent_reviews WHERE agent_id = a.id AND is_approved = 1) AS avg_rating,
            (SELECT COUNT(*) FROM agent_reviews WHERE agent_id = a.id AND is_approved = 1) AS review_count,
            (SELECT COUNT(*) FROM agent_leads WHERE agent_id = a.id) AS leads_count
        FROM agents AS a
        LEFT JOIN agent_profiles AS ap ON a.id = ap.agent_id
        LEFT JOIN agent_subscriptions AS s ON a.id = s.agent_id
            AND s.id = (SELECT MAX(id) FROM agent_subscriptions WHERE agent_id = a.id)
        WHERE 1=1
    """
    params = []

    if search:
        query += " AND (a.fullname LIKE %s OR a.email LIKE %s OR a.mobile LIKE %s OR ap.display_name LIKE %s)"
        search_param = f"%{search}%"
        params.extend([search_param, search_param, search_param, search_param])

    if plan_filter and plan_filter != "All Plans":
        if plan_filter == PLAN_LABELS["professional"]:
            query += " AND (s.selected_plan = %s OR LOWER(a.plan_type) IN ('professional', 'pro'))"
            params.append(plan_filter)
        elif plan_filter == PLAN_LABELS["starter"]:
            query += " AND (s.selected_plan = %s OR LOWER(a.plan_type) IN ('basic', 'starter', 'standard'))"
            params.append(plan_filter)
        else:
            query += " AND s.selected_plan = %s"
            params.append(plan_filter)

    # Status Filter logic
    if status_filter == "blacklisted":
        query += " AND a.is_blacklisted = 1"
    elif status_filter == "not_blacklisted":
        query += " AND (a.is_blacklisted = 0 OR a.is_blacklisted IS NULL)"
    elif status_filter and status_filter != "All Status":
        query += " AND a.status = %s"
        params.append(status_filter)
    elif not status_filter and not promo_code_filter:
        # Default behavior if status_filter is None/empty and no promo code filter: only active agents
        query += " AND a.status = 'active'"

    if promo_code_filter:
        query += """ AND (
            EXISTS (SELECT 1 FROM invoices WHERE invoices.agent_id = a.id AND invoices.promo_code = %s)
            OR
            EXISTS (SELECT 1 FROM free_trial_history WHERE free_trial_history.agent_id = a.id AND free_trial_history.promo_code = %s)
            OR
            EXISTS (SELECT 1 FROM agent_subscriptions WHERE agent_subscriptions.agent_id = a.id AND agent_subscriptions.promo_code = %s)
            OR
            a.referred_by_code = %s
        )"""
        params.extend(
            [promo_code_filter, promo_code_filter, promo_code_filter, promo_code_filter]
        )

    if city_filter:
        query += " AND ap.address LIKE %s"
        params.append(f"%{city_filter}%")

    query += " ORDER BY a.id DESC"

    return query, params


def _apply_resolved_plan_label(agent_row):
    if not agent_row:
        return
    label = resolve_agent_display_plan_label(
        agent_row.get("plan_type"),
        agent_row.get("selected_plan"),
    )
    agent_row["selected_plan"] = label or agent_row.get("selected_plan") or "FREE"


class _RawAgentPage:
    """Lazy rows for Paginator: COUNT(*) for the total and LIMIT/OFFSET for
    one page, instead of loading every agent (with three correlated
    subqueries each) to show 25 (audit 2026-10-01 F-37)."""

    def __init__(self, query, params):
        self.query = query
        self.params = list(params)
        self._count = None

    def count(self):
        if self._count is None:
            body = self.query[self.query.index("FROM agents AS a") :]
            order_at = body.rfind(" ORDER BY ")
            if order_at != -1:
                body = body[:order_at]
            try:
                self._count = fetch_agent_list_count(body, self.params)
            except Exception as e:
                logger.error(f"Error counting agents list: {e}")
                self._count = 0
        return self._count

    def __len__(self):
        return self.count()

    def __getitem__(self, key):
        if not isinstance(key, slice):
            rows = self[key : key + 1]
            if not rows:
                raise IndexError(key)
            return rows[0]
        start = max(key.start or 0, 0)
        stop = self.count() if key.stop is None else key.stop
        if stop <= start:
            return []
        try:
            rows = fetch_agent_list_page(self.query, self.params, stop - start, start)
            for row in rows:
                _apply_resolved_plan_label(row)
            return rows
        except Exception as e:
            logger.error(f"Error fetching agents list: {e}")
            return []


def agent_list(request):
    """
    Phase 3B: Active Agents Listing View
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    search = request.GET.get("search", "")
    plan_filter = request.GET.get("plan", "All Plans")
    status_filter = (request.GET.get("status") or "").strip() or "active"
    city_filter = request.GET.get("city", "")
    promo_code_filter = request.GET.get("promo_code", "")

    query, params = _build_agent_list_query(
        search, plan_filter, status_filter, city_filter, promo_code_filter
    )

    paginator = Paginator(_RawAgentPage(query, params), 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "agents": page_obj.object_list,
        "search": search,
        "plan_filter": plan_filter,
        "status_filter": status_filter,
        "city_filter": city_filter,
        "promo_code": promo_code_filter,
        "page_obj": page_obj,
    }

    return render(request, "admin/agents/list.html", context)


def manage_agent(request, id):
    """
    Phase 3C: Manage Agent View (Read-Only)
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    # 1. Fetch Agent Details via raw SQL mimicking Laravel's showManageAgent
    agent = None
    try:
        row = fetch_agent_detail(id)
        if row:
            agent = row
            _apply_resolved_plan_label(agent)
    except Exception as e:
        logger.error(f"Error fetching agent details: {e}")

    if not agent:
        return redirect("admin_agents")

    # 2. Fetch Recent Reviews via Raw SQL mimicking Laravel's showManageAgent
    reviews = []
    try:
        reviews = fetch_agent_recent_reviews(id)
    except Exception as e:
        logger.error(f"Error fetching agent reviews: {e}")

    # 3. Fetch Edit Logs using ORM
    # from admin_panel.models.agent_profile_edit_log import AgentProfileEditLog
    from ..models.agent_profile_edit_log import AgentProfileEditLog
    import json

    edit_logs_raw = AgentProfileEditLog.objects.filter(agent_id=id).order_by(
        "-created_at", "-id"
    )[:50]

    edit_logs = []
    for log in edit_logs_raw:
        parsed_changes = []
        if log.changes:
            if isinstance(log.changes, (list, dict)):
                parsed_changes = log.changes
            elif isinstance(log.changes, (str, bytes, bytearray)):
                try:
                    parsed_changes = json.loads(log.changes)
                except (json.JSONDecodeError, TypeError):
                    parsed_changes = []

        edit_logs.append(
            {
                "id": log.id,
                "step": log.step,
                "step_label": log.step_label,
                "changes": parsed_changes,
                "status_before": log.status_before,
                "status_after": log.status_after,
                "edited_by": log.edited_by,
                "created_at": log.created_at,
            }
        )

    # Parse investment_types JSON if it is a string
    if agent and "investment_types" in agent:
        import json

        inv_types = agent["investment_types"]
        if isinstance(inv_types, str):
            try:
                agent["investment_types"] = json.loads(inv_types)
            except Exception:
                agent["investment_types"] = []
        elif inv_types is None:
            agent["investment_types"] = []

    context = {
        "agent": agent,
        "reviews": reviews,
        "edit_logs": edit_logs,
    }

    return render(request, "admin/agents/manage.html", context)


# Every status an agent row can legitimately hold. Anything else is a typo or
# tampering and would silently hide the agent from every admin queue.
AGENT_STATUSES = (
    "incomplete",
    "pending_payment",
    "pending_approval",
    "pending_admin_approval",
    "pending_accounts_payment",
    "event_challenge",
    "active",
    "inactive",
    "suspended",
    "blacklisted",
    "rejected",
    "deleted",
    "expired",
)
# What a staff admin with only the Approvals permission may do from the queue.
QUEUE_DECISIONS = ("active", "suspended", "rejected")


def _admin_can_manage_all_agents(request):
    admin = getattr(request, "admin_user", None)  # set by AdminPermissionMiddleware
    if admin is None or getattr(admin, "role", "") == "super":
        return True
    perms = admin.permissions if isinstance(admin.permissions, list) else []
    return "agents" in perms


def _payment_note(agent_id):
    from apps.agents.models import AgentSubscription

    sub = (
        AgentSubscription.objects.filter(
            agent_id=agent_id, payment_status=PaymentStatus.COMPLETED
        )
        .order_by("-created_at")
        .first()
    )
    if not sub:
        return "no completed payment"
    return f"paid subscription #{sub.pk} ({sub.selected_plan}, order {sub.razorpay_order_id or '-'})"


def toggle_status(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method"})

    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({"success": False, "message": "Unauthorized"})

    try:
        data = json.loads(request.body)
        agent_id = data.get("id")
        new_status = data.get("status")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON"})

    if not agent_id or not new_status:
        return JsonResponse({"success": False, "message": "Missing data"})
    if new_status not in AGENT_STATUSES:
        return JsonResponse(
            {"success": False, "message": "Unknown status."}, status=400
        )

    # Fetch agent to get old_status
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT status FROM agents WHERE id = %s", [agent_id])
            row = cursor.fetchone()
            if not row:
                return JsonResponse({"success": False, "message": "Agent not found"})
            old_status = row[0]

            # Approvals-only staff decide queue entries; they cannot change
            # other agents (the route also admits the Approvals permission).
            if not _admin_can_manage_all_agents(request) and not (
                old_status == "pending_approval" and new_status in QUEUE_DECISIONS
            ):
                return JsonResponse(
                    {
                        "success": False,
                        "message": "You can only approve or reject agents awaiting approval.",
                    },
                    status=403,
                )

            # Update status only if nobody changed it meanwhile: a double-clicked Approve
            # otherwise ran twice and sent two WhatsApp approval messages.
            if new_status == "active":
                cursor.execute(
                    "UPDATE agents SET status = %s, is_approved = 1, approved_at = COALESCE(approved_at, %s) WHERE id = %s AND status = %s",
                    [new_status, timezone.now(), agent_id, old_status],
                )
            else:
                cursor.execute(
                    "UPDATE agents SET status = %s WHERE id = %s AND status = %s",
                    [new_status, agent_id, old_status],
                )
            if cursor.rowcount == 0:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "This agent's status was just changed. Refresh the page.",
                    },
                    status=409,
                )
            cache.delete("homepage_reviews")
    except Exception as e:
        logger.error(f"Error updating agent status: {e}")
        return JsonResponse({"success": False, "message": "Database error"})

    agents_service.after_status_change(
        agent_id, admin_id, request.META.get("REMOTE_ADDR"), old_status, new_status
    )

    from apps.admin_panel.models import AdminActivityLog

    AdminActivityLog.log(
        f"Agent status {old_status} -> {new_status}",
        "Agent",
        int(agent_id),
        details=_payment_note(agent_id),
        request=request,
    )
    return JsonResponse({"success": True})


def bulk_action_agents(request):
    if request.method != "POST":
        return redirect("admin_agents_approvals")

    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    action = request.POST.get("action")
    agent_ids = request.POST.getlist("agent_ids[]")

    if not agent_ids:
        messages.error(request, "No agents selected.")
        return redirect("admin_agents_approvals")

    if action == "approve":
        try:
            agent_ids, skipped, old_statuses = agents_service.bulk_approve_pending(
                agent_ids
            )
            if not agent_ids:
                messages.error(
                    request, "None of the selected agents are awaiting approval."
                )
                return redirect("admin_agents_approvals")

            from apps.admin_panel.models import AdminActivityLog

            for aid in agent_ids:
                AdminActivityLog.log(
                    "Agent status pending_approval -> active (bulk)",
                    "Agent",
                    int(aid),
                    details=_payment_note(aid),
                    request=request,
                )
                agents_service.notify_approved_whatsapp(aid)

            agents_service.log_bulk_approvals(
                agent_ids, old_statuses, admin_id, request.META.get("REMOTE_ADDR")
            )
            messages.success(
                request,
                "Selected agents have been approved."
                + (
                    f" {skipped} not awaiting approval were skipped." if skipped else ""
                ),
            )
        except Exception as e:
            logger.error(f"Bulk approve error: {e}")
            messages.error(request, "Failed to bulk approve agents.")

    return redirect("admin_agents_approvals")


def update_badge(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method"})

    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({"success": False, "message": "Unauthorized"})

    try:
        data = json.loads(request.body)
        agent_id = data.get("id")
        badge_data = data.get("badge")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON"})

    if not agent_id:
        return JsonResponse({"success": False, "message": "Missing agent ID"})

    if isinstance(badge_data, list):
        # Filter empty values and join by comma
        badge_value = ",".join(filter(None, badge_data))
    else:
        badge_value = badge_data if badge_data else ""

    try:
        if not agents_service.update_badge(agent_id, badge_value):
            return JsonResponse({"success": False, "message": "Agent not found"})
    except Exception as e:
        logger.error(f"Error updating agent badge: {e}")
        return JsonResponse({"success": False, "message": "Database error"})

    return JsonResponse({"success": True})


def update_irdai_license(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method"})

    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({"success": False, "message": "Unauthorized"})

    try:
        data = json.loads(request.body)
        agent_id = data.get("id")
        license_number = data.get("license_number")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON"})

    if not agent_id or license_number is None:
        return JsonResponse({"success": False, "message": "Missing required fields"})

    license_number = license_number.strip()

    try:
        if not agents_service.update_irdai_license(agent_id, license_number):
            return JsonResponse({"success": False, "message": "Agent not found"})
        return JsonResponse(
            {
                "success": True,
                "message": "IRDAI license number updated successfully.",
            }
        )
    except Exception as e:
        logger.error(f"Error updating agent IRDAI license: {e}")
        return JsonResponse({"success": False, "message": "Database error."})


def save_agent_notes(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method"})

    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({"success": False, "message": "Unauthorized"})

    try:
        data = json.loads(request.body)
        agent_id = data.get("id")
        notes = data.get("notes")
        admin_notes = data.get("admin_notes")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON"})

    if not agent_id:
        return JsonResponse({"success": False, "message": "Missing agent ID"})

    final_notes = notes if notes is not None else admin_notes

    try:
        if not agents_service.save_agent_notes(agent_id, final_notes):
            return JsonResponse({"success": False, "message": "Agent not found"})
    except Exception as e:
        logger.error(f"Error saving agent notes: {e}")
        return JsonResponse({"success": False, "message": "Database error"})

    return JsonResponse({"success": True})


def update_visibility(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method"})

    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({"success": False, "message": "Unauthorized"})

    try:
        data = json.loads(request.body)
        field = data.get("field")
        value = 1 if data.get("value") else 0
        agent_id = data.get("id")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON"})

    valid_fields = [
        "is_profile_visible",
        "is_card_visible",
        "show_certificates",
        "show_achievements",
        "show_reviews",
        "show_experience",
        "show_claims_stats",
        "show_client_base",
        "show_ratings",
        "show_languages",
        "show_gallery",
        "show_contact_info",
        "show_social_links",
    ]
    if field not in valid_fields:
        return JsonResponse({"success": False, "message": "Invalid field"})

    try:
        agents_service.update_visibility(field, value, agent_id)
    except Exception as e:
        logger.error(f"Error updating agent visibility: {e}")
        return JsonResponse({"success": False, "message": "Database error"})

    if field in ("is_profile_visible", "show_reviews"):
        cache.delete("homepage_reviews")

    return JsonResponse({"success": True})


def update_achievement_limit(request):
    if request.method != "POST":
        return redirect("admin_dashboard")

    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    agent_id = request.POST.get("id")
    raw_limit = request.POST.get("achievement_photo_limit")

    if not agent_id:
        messages.error(request, "Agent ID is required.")
        return redirect("admin_agents")

    agent_id = int(agent_id)

    # Check if the column exists
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW COLUMNS FROM agents LIKE 'achievement_photo_limit'")
            if not cursor.fetchone():
                messages.error(
                    request,
                    "Achievement limit column not found. Please run database migration first.",
                )
                return redirect("admin_agents_manage", id=agent_id)

            cursor.execute("SELECT id FROM agents WHERE id = %s", [agent_id])
            if not cursor.fetchone():
                messages.error(request, "Agent not found.")
                return redirect("admin_agents")

            cursor.execute(
                "SELECT selected_plan FROM agent_subscriptions WHERE agent_id = %s ORDER BY id DESC LIMIT 1",
                [agent_id],
            )
            plan_row = cursor.fetchone()
            selected_plan = plan_row[0] if plan_row else ""

    except Exception as e:
        logger.error(f"Error checking achievement limit schema: {e}")
        messages.error(request, "Database error.")
        return redirect("admin_agents_manage", id=agent_id)

    plan_text = str(selected_plan).lower()
    default_limit = 10 if "professional" in plan_text else 5

    new_limit = int(raw_limit) if raw_limit and raw_limit.strip() else None

    if new_limit is not None and new_limit < default_limit:
        messages.error(
            request,
            f"Custom limit cannot be lower than the default {default_limit} for this plan.",
        )
        return redirect("admin_agents_manage", id=agent_id)

    try:
        agents_service.set_achievement_limit(agent_id, new_limit)
    except Exception as e:
        logger.error(f"Error updating agent achievement limit: {e}")
        messages.error(request, "Database error updating limit.")
        return redirect("admin_agents_manage", id=agent_id)

    effective = new_limit if new_limit is not None else default_limit
    messages.success(
        request,
        f"Achievement photo limit updated successfully. Effective limit: {effective}",
    )
    return redirect("admin_agents_manage", id=agent_id)


def update_plan(request):
    if request.method != "POST":
        return redirect("admin_dashboard")

    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    agent_id = request.POST.get("id")
    new_plan = request.POST.get("selected_plan")
    if new_plan:
        label = paid_plan_label(new_plan)
        if label in (PLAN_LABELS["starter"], PLAN_LABELS["professional"]):
            new_plan = label

    if not agent_id or new_plan is None:
        messages.error(request, "Agent ID is required.")
        return redirect("admin_agents")

    try:
        agent_id = int(agent_id)
    except (TypeError, ValueError):
        messages.error(request, "Invalid agent ID.")
        return redirect("admin_agents")

    # Free text here was stored verbatim and later rendered on the dashboard (stored XSS).
    if new_plan and new_plan not in PLAN_LABELS.values():
        messages.error(request, "Unknown plan.")
        return redirect("admin_agents_manage", id=agent_id)

    from apps.admin_panel.models import AdminActivityLog

    # Map the chosen plan to agents.plan_type (what feature unlocks read).
    plan_slug = plan_slug_from_name(new_plan or "")
    # Granting a paid plan without payment is the same power as mark_payment: Super Admin only.
    from .pages import _is_super_admin

    if plan_slug in ("starter", "professional", "exclusive") and not _is_super_admin(
        admin_id
    ):
        messages.error(request, "Only a Super Admin can assign a paid plan.")
        return redirect("admin_agents_manage", id=agent_id)
    if not new_plan:
        plan_type = ""  # "No Plan" (was 'standard', i.e. Starter features)
    elif plan_slug == "starter":
        plan_type = "basic"
    elif plan_slug in ("professional", "exclusive"):
        plan_type = plan_slug  # exclusive used to fall through to 'standard'
    elif "trial" in new_plan.lower():
        plan_type = "free_trial"
    else:
        plan_type = "standard"

    try:
        old_plan = agents_service.apply_plan_change(agent_id, new_plan, plan_type)

        AdminActivityLog.log(
            "Admin changed agent plan",
            "Agent",
            agent_id,
            details=f"{old_plan or '(none)'} -> {new_plan or '(no plan)'}; plan_type={plan_type or '(none)'}",
            request=request,
        )
    except Exception as e:
        logger.error(f"Error updating agent plan: {e}")
        messages.error(request, "Database error updating plan.")
        return redirect("admin_agents_manage", id=agent_id)

    messages.success(request, "Subscription plan updated successfully.")
    return redirect("admin_agents_manage", id=agent_id)


def toggle_review_approval(request):
    if request.method != "POST":
        return redirect("admin_dashboard")

    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    review_id = request.POST.get("review_id")
    is_approved = request.POST.get("is_approved")
    agent_id = request.POST.get("agent_id")  # To redirect back properly

    if not review_id or is_approved is None:
        messages.error(request, "Missing review approval parameters.")
        if agent_id:
            return redirect("admin_agents_manage", id=agent_id)
        return redirect("admin_agents")

    try:
        agents_service.set_review_approval(review_id, is_approved)
    except Exception as e:
        logger.error(f"Error toggling review approval: {e}")
        messages.error(request, "Database error.")
        if agent_id:
            return redirect("admin_agents_manage", id=agent_id)
        return redirect("admin_agents")

    messages.success(request, "Review status updated.")
    if agent_id:
        return redirect("admin_agents_manage", id=agent_id)
    return redirect("admin_agents")


def update_profile(request):
    if request.method != "POST":
        return redirect("admin_dashboard")

    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    agent_id = request.POST.get("id")
    fullname = request.POST.get("fullname")
    email = request.POST.get("email")
    mobile = request.POST.get("mobile")
    experience_range = request.POST.get("experience_range")
    address = request.POST.get("address")
    office_address = request.POST.get("office_address")
    license_number = request.POST.get("license_number")
    pan_number = request.POST.get("pan_number")

    license_valid_till = request.POST.get("license_valid_till") or None
    arn_number = request.POST.get("arn_number", "").strip()
    euin_number = request.POST.get("euin_number", "").strip()
    investment_valid_till = request.POST.get("investment_valid_till") or None
    investment_types = request.POST.getlist(
        "investment_types[]"
    ) or request.POST.getlist("investment_types")

    if not agent_id:
        messages.error(request, "Agent ID is required.")
        return redirect("admin_agents")

    try:
        agent_id = int(agent_id)
    except (TypeError, ValueError):
        messages.error(request, "Invalid agent ID.")
        return redirect("admin_agents")

    from apps.agents.models import Agent
    from apps.agents.views.dashboard import _email_taken_by_other_login

    agent = Agent.objects.filter(pk=agent_id).first()
    if not agent:
        messages.error(request, "Agent not found.")
        return redirect("admin_agents")
    email = (email or "").strip()
    if not email:
        messages.error(request, "Email is required.")
        return redirect("admin_agents_manage", id=agent_id)
    previous_email = agent.email
    # CLAUDE.md invariant 6: login resolves agents by email, so a shared address hands over the dashboard.
    if email.lower() != (previous_email or "").lower() and (
        _email_taken_by_other_login(email, agent)
        or Agent.objects.filter(email__iexact=email).exclude(pk=agent_id).exists()
    ):
        messages.error(request, "That email already belongs to another account.")
        return redirect("admin_agents_manage", id=agent_id)

    try:
        agents_service.update_agent_profile(
            agent_id,
            previous_email,
            fullname,
            email,
            mobile,
            experience_range,
            address,
            office_address,
            license_number,
            pan_number,
            license_valid_till,
            arn_number,
            euin_number,
            investment_valid_till,
            investment_types,
        )
    except Exception as e:
        logger.error(f"Error updating agent profile: {e}")
        messages.error(request, "Database error updating profile.")
        return redirect("admin_agents_manage", id=agent_id)

    messages.success(request, "Agent profile updated successfully.")
    return redirect("admin_agents_manage", id=agent_id)


def get_agent_json(request, id):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({"success": False, "message": "Unauthorized"})

    try:
        agent = fetch_agent_json(id)
        if agent:
            return JsonResponse({"success": True, "agent": agent})

    except Exception as e:
        logger.error(f"Error getting agent json: {e}")

    return JsonResponse({"success": False})


from django.utils.timesince import timesince
from django.utils.html import escape
from django.db.models import Q


def get_edit_logs(request, id):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({"success": False, "message": "Unauthorized"})

    try:
        from ..models.agent_profile_edit_log import AgentProfileEditLog

        # Step 1: Find the last time admin approved this agent
        last_approved = (
            AgentProfileEditLog.objects.filter(
                agent_id=id, edited_by="admin", step__isnull=True, status_after="active"
            )
            .order_by("-created_at")
            .first()
        )

        last_approved_at = last_approved.created_at if last_approved else None

        # Build query
        query = AgentProfileEditLog.objects.filter(agent_id=id).exclude(
            edited_by="admin_marker"
        )

        # Exclude boundary log entries themselves (empty changes, admin action)
        query = query.filter(
            Q(edited_by="agent") | Q(edited_by="admin", step__isnull=False)
        ).order_by("-created_at")

        if last_approved_at:
            query = query.filter(created_at__gt=last_approved_at)

        logs_data = []
        for log in query:
            changes = []
            if log.changes:
                if isinstance(log.changes, (list, dict)):
                    changes = log.changes
                elif isinstance(log.changes, (str, bytes, bytearray)):
                    try:
                        changes = json.loads(log.changes)
                    except (json.JSONDecodeError, TypeError):
                        pass
            # The drawer renders these via innerHTML and the values are agent-typed.
            if isinstance(changes, list):
                changes = [
                    {k: escape(v) if isinstance(v, str) else v for k, v in ch.items()}
                    for ch in changes
                    if isinstance(ch, dict)
                ]

            diff_for_humans = (
                timesince(log.created_at) + " ago" if log.created_at else ""
            )
            created_at_str = (
                log.created_at.strftime("%d %b %Y, %I:%M %p") if log.created_at else ""
            )

            logs_data.append(
                {
                    "id": log.id,
                    "step_label": log.step_label if log.step_label else "Profile Edit",
                    "step": log.step,
                    "edited_by": log.edited_by,
                    "changes": changes,
                    "status_before": log.status_before,
                    "status_after": log.status_after,
                    "ip_address": log.ip_address,
                    "created_at": created_at_str,
                    "diff_for_humans": diff_for_humans,
                }
            )

        return JsonResponse({"success": True, "logs": logs_data})

    except Exception as e:
        logger.error(f"Error getting edit logs json: {e}")
        logger.exception("Admin request failed in agents")  # detail stays server-side
        return JsonResponse(
            {
                "success": False,
                "message": "Something went wrong. Details are in the server log.",
            }
        )


def _build_queue_query(
    status_filter,
    search,
    plan_filter,
    city_filter,
    event_filter,
    sort_by,
    light=False,
    only_ids=None,
):
    """light: only the columns needed to sort, count and paginate (skips the per-row
    event/blacklist/review subqueries). only_ids: restrict to these agent ids."""
    from django.db import connection

    if connection.vendor == "sqlite":
        hours_expr = (
            "CAST((julianday('now') - julianday(a.created_at)) * 24 AS INTEGER)"
        )
        minutes_expr = (
            "CAST((julianday('now') - julianday(s.created_at)) * 1440 AS INTEGER)"
        )
    else:
        hours_expr = "TIMESTAMPDIFF(HOUR, a.created_at, NOW())"
        minutes_expr = "TIMESTAMPDIFF(MINUTE, s.created_at, NOW())"

    full_columns = f"""
            a.id, a.fullname, a.email, a.mobile, a.status, a.plan_type, a.event_id,
            (SELECT e.name FROM events e WHERE e.id = a.event_id LIMIT 1) AS event_name,
            a.created_at, a.updated_at, a.badge, a.registration_step, a.is_blacklisted,
            ap.address, ap.display_name, ap.profile_photo_path, ap.pan_number,
            (SELECT COUNT(*) FROM blacklisted_agents WHERE pan = ap.pan_number AND ap.pan_number IS NOT NULL AND ap.pan_number != '') as is_blacklisted_by_pan,
            s.selected_plan, s.expires_at,
            s.razorpay_order_id, s.razorpay_payment_id, s.payment_status as sub_payment_status,
            s.created_at as sub_created_at, s.registration_amount,
            (SELECT AVG(rating) FROM agent_reviews WHERE agent_id = a.id AND is_approved = 1) as avg_rating,
            (SELECT COUNT(*) FROM agent_reviews WHERE agent_id = a.id AND is_approved = 1) as review_count,
            {hours_expr} as hours_waiting,
            {minutes_expr} as sub_minutes_ago"""
    light_columns = f"""
            a.id, a.created_at, a.status, s.razorpay_order_id,
            s.payment_status as sub_payment_status, {hours_expr} as hours_waiting"""
    query = f"""
        SELECT {light_columns if light else full_columns}
        FROM agents as a
        LEFT JOIN agent_profiles as ap ON a.id = ap.agent_id
        LEFT JOIN agent_subscriptions as s ON a.id = s.agent_id
            AND s.id = COALESCE(
                (SELECT MAX(id) FROM agent_subscriptions WHERE agent_id = a.id AND payment_status = 'completed'),
                (SELECT MAX(id) FROM agent_subscriptions WHERE agent_id = a.id)
            )
        WHERE 1=1
    """
    params = []

    if isinstance(status_filter, list):
        query += " AND a.status IN (" + ",".join(["%s"] * len(status_filter)) + ")"
        params.extend(status_filter)
    else:
        query += " AND a.status = %s"
        params.append(status_filter)

    if only_ids is not None:
        ids = [int(i) for i in only_ids] or [0]
        query += " AND a.id IN (" + ",".join(["%s"] * len(ids)) + ")"
        params.extend(ids)

    if search:
        query += (
            " AND (a.fullname LIKE %s OR a.email LIKE %s OR ap.display_name LIKE %s)"
        )
        search_param = f"%{search}%"
        params.extend([search_param, search_param, search_param])

    if plan_filter and plan_filter != "All Plans":
        if plan_filter == PLAN_LABELS["professional"]:
            query += " AND (s.selected_plan = %s OR LOWER(a.plan_type) IN ('professional', 'pro'))"
            params.append(plan_filter)
        elif plan_filter == PLAN_LABELS["starter"]:
            query += " AND (s.selected_plan = %s OR LOWER(a.plan_type) IN ('basic', 'starter', 'standard'))"
            params.append(plan_filter)
        else:
            query += " AND s.selected_plan = %s"
            params.append(plan_filter)

    if city_filter:
        query += " AND ap.address LIKE %s"
        params.append(f"%{city_filter}%")

    event_sql, event_params = _event_filter_sql(event_filter)
    query += event_sql
    params.extend(event_params)

    if sort_by == "oldest":
        query += " ORDER BY a.created_at ASC"
    elif sort_by == "waiting":
        query += f" ORDER BY {hours_expr} DESC"
    else:
        query += " ORDER BY a.created_at DESC"

    return query, params


def _event_filter_sql(event_filter):
    """SQL fragment + params for admin event_id filters (includes Paldi challengers)."""
    if not event_filter or event_filter == "All Events":
        return "", []
    try:
        event_id_int = int(event_filter)
    except (TypeError, ValueError):
        return " AND a.event_id = %s", [event_filter]

    paldi_id = None
    try:
        from apps.event_referral.services.paldi_event import get_or_create_paldi_event

        paldi_id = get_or_create_paldi_event().id
    except Exception:
        pass

    if paldi_id is not None and event_id_int == paldi_id:
        return (
            " AND (a.event_id = %s OR a.id IN (SELECT agent_id FROM event_referral_participants))",
            [event_id_int],
        )
    return " AND a.event_id = %s", [event_id_int]


def _get_events_list():
    events = []
    try:
        events = fetch_event_names()
    except Exception:
        pass
    try:
        from apps.event_referral.services.paldi_event import get_or_create_paldi_event

        paldi = get_or_create_paldi_event()
        if not any(e.get("id") == paldi.id for e in events):
            events.append({"id": paldi.id, "name": paldi.name})
            events.sort(key=lambda e: (e.get("name") or "").lower())
    except Exception:
        pass
    return events


MISSING_IRDAI_LIMIT = 200


def agent_approvals(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    search = request.GET.get("search", "")
    plan_filter = request.GET.get("plan", "All Plans")
    sort_by = request.GET.get("sort", "newest")
    city_filter = request.GET.get("city", "")
    event_filter = request.GET.get("event_id", "All Events")

    query, params = _build_queue_query(
        "pending_approval", search, plan_filter, city_filter, event_filter, sort_by
    )

    agents = []
    total_pending = 0
    urgent_count = 0
    total_wait_hours = 0

    try:
        agents = fetch_queue_rows(query, params)
    except Exception as e:
        logger.error(f"Error fetching approvals list: {e}")

    for agent in agents:
        _apply_resolved_plan_label(agent)
        total_pending += 1
        hours_waiting = agent.get("hours_waiting") or 0
        total_wait_hours += hours_waiting
        if hours_waiting > 48:
            urgent_count += 1

    avg_wait_hours = (total_wait_hours / total_pending) if total_pending > 0 else 0

    missing_irdai_agents = []
    missing_irdai_total = 0
    try:
        missing_irdai_total = count_missing_irdai_agents()
        missing_irdai_agents = fetch_missing_irdai_agents(MISSING_IRDAI_LIMIT)
    except Exception as e:
        logger.error(f"Error fetching missing IRDAI agents: {e}")

    for agent in missing_irdai_agents:
        badge_str = agent.get("badge") or ""
        agent["badges"] = [b for b in badge_str.split(",") if b]
        agent["initials"] = agent["fullname"][0].upper() if agent["fullname"] else "A"

    context = {
        "agents": agents,
        "search": search,
        "plan_filter": plan_filter,
        "city_filter": city_filter,
        "event_filter": event_filter,
        "sort_by": sort_by,
        "events": _get_events_list(),
        "totalPending": total_pending,
        "urgentCount": urgent_count,
        "avgWaitHours": avg_wait_hours,
        "missingIrdaiAgents": missing_irdai_agents,
        "missingIrdaiTotal": missing_irdai_total,
    }

    return render(request, "admin/agents/approvals.html", context)


def agent_pending_registrations(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    search = request.GET.get("search", "")
    plan_filter = request.GET.get("plan", "All Plans")
    sort_by = request.GET.get("sort", "newest")
    city_filter = request.GET.get("city", "")
    event_filter = request.GET.get("event_id", "All Events")

    pending_statuses = ["incomplete", "pending_payment", "event_challenge"]
    # Light rows for every pending agent (sort, stats, pagination); full rows for the page only.
    query, params = _build_queue_query(
        pending_statuses,
        search,
        plan_filter,
        city_filter,
        event_filter,
        sort_by,
        light=True,
    )

    agents = []
    total_pending = 0
    urgent_count = 0
    total_wait_hours = 0
    payment_initiated_count = 0

    try:
        agents = fetch_queue_rows(query, params)
    except Exception as e:
        logger.error(f"Error fetching pending registrations list: {e}")

    # ── Also fetch AgentDraft entries (Step 1 done, plan not yet chosen) ──
    # Only include drafts whose email does NOT already exist in the agents table.
    draft_entries = []
    if (not plan_filter or plan_filter == "All Plans") and (
        not event_filter or event_filter == "All Events"
    ):
        try:
            raw_drafts = fetch_pending_drafts(search, city_filter, sort_by)
            for d in raw_drafts:
                reg_step = d.get("registration_step") or 1
                is_claimed = reg_step >= 2
                draft_entries.append(
                    {
                        "id": d["id"],
                        "fullname": d["fullname"] or "",
                        "email": d["email"] or "",
                        "mobile": d["mobile"] or "",
                        "status": "claim" if is_claimed else "draft",
                        "registration_step": reg_step,
                        "draft_badge": "CLAIM" if is_claimed else "DRAFT",
                        "is_claimed": is_claimed,
                        "address": d.get("address") or d.get("state") or "",
                        "display_name": d["fullname"] or "",
                        "profile_photo_path": None,
                        "pan_number": None,
                        "is_blacklisted": False,
                        "is_blacklisted_by_pan": 0,
                        "badge": None,
                        "selected_plan": None,
                        "razorpay_order_id": None,
                        "sub_payment_status": None,
                        "sub_created_at": None,
                        "sub_minutes_ago": None,
                        "registration_amount": None,
                        "avg_rating": None,
                        "review_count": 0,
                        "created_at": d["created_at"],
                        "updated_at": d["updated_at"],
                        "hours_waiting": d.get("hours_waiting") or 0,
                        "is_draft": True,
                        "last_event": "",
                        "event_label": "",
                    }
                )
        except Exception as _e:
            logger.error(f"Error fetching draft registrations: {_e}")

    # Merge and re-sort
    all_entries = agents + draft_entries
    if sort_by == "oldest":
        all_entries.sort(key=lambda x: str(x.get("created_at") or ""), reverse=False)
    elif sort_by == "waiting":
        all_entries.sort(key=lambda x: x.get("hours_waiting") or 0, reverse=True)
    else:
        all_entries.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)

    # Agents + drafts are merged in Python, so paginate the list; stats below still cover all entries.
    page_obj = Paginator(all_entries, 25).get_page(request.GET.get("page"))
    page_entries = list(page_obj.object_list)

    page_agent_ids = [e["id"] for e in page_entries if not e.get("is_draft")]
    full_by_id = {}
    if page_agent_ids:
        try:
            full_query, full_params = _build_queue_query(
                pending_statuses,
                search,
                plan_filter,
                city_filter,
                event_filter,
                sort_by,
                only_ids=page_agent_ids,
            )
            full_by_id = {
                row["id"]: row for row in fetch_queue_rows(full_query, full_params)
            }
        except Exception as e:
            logger.error(f"Error fetching pending registrations page: {e}")
    for i, entry in enumerate(page_entries):
        if not entry.get("is_draft") and entry["id"] in full_by_id:
            page_entries[i] = full_by_id[entry["id"]]
            _apply_resolved_plan_label(page_entries[i])
    page_obj.object_list = page_entries

    # ── Bulk-fetch latest RegistrationActivityLog event per entry ──
    _EVENT_LABELS = {
        "FORM_SUBMIT": "Form Submitted",
        "PENDING_FOR_REGISTRATION": "Pending Payment",
        "DISTRIBUTION": "Distributor Assigned",
        "CLAIM_BUTTON": "Choosing Plan",
        "PAYMENT_BUTTON": "Payment Done",
    }
    _STATUS_LABELS = {
        "event_challenge": "Paldi — Referral challenge",
    }
    draft_event_map = {}
    agent_event_map = {}
    _draft_ids = [str(e["id"]) for e in page_entries if e.get("is_draft")]
    _agent_ids = [str(e["id"]) for e in page_entries if not e.get("is_draft")]
    try:
        if _draft_ids:
            draft_event_map = fetch_latest_draft_events(_draft_ids)
        if _agent_ids:
            agent_event_map = fetch_latest_agent_events(_agent_ids)
    except Exception as _e:
        logger.warning(f"Event lookup failed: {_e}")

    for entry in page_entries:
        _eid = str(entry.get("id", ""))
        last_ev = (
            draft_event_map.get(_eid, "")
            if entry.get("is_draft")
            else agent_event_map.get(_eid, "")
        )
        entry["last_event"] = last_ev
        entry["event_label"] = _EVENT_LABELS.get(last_ev, "")
        if entry.get("status") == "event_challenge":
            entry["event_label"] = (
                entry.get("event_name") or _STATUS_LABELS["event_challenge"]
            )
        elif entry.get("event_name"):
            entry["event_label"] = entry["event_name"]
        if last_ev == "CLAIM_BUTTON" and entry.get("is_draft"):
            entry["draft_badge"] = "CLAIM"
            entry["is_claimed"] = True

    for entry in all_entries:
        total_pending += 1
        hours_waiting = entry.get("hours_waiting") or 0
        total_wait_hours += hours_waiting
        if hours_waiting > 48:
            urgent_count += 1
        if (
            entry.get("razorpay_order_id")
            and entry.get("sub_payment_status") == "pending"
        ):
            payment_initiated_count += 1

    avg_wait_hours = (total_wait_hours / total_pending) if total_pending > 0 else 0

    context = {
        "agents": page_entries,
        "page_obj": page_obj,
        "search": search,
        "plan_filter": plan_filter,
        "city_filter": city_filter,
        "event_filter": event_filter,
        "sort_by": sort_by,
        "events": _get_events_list(),
        "totalPending": total_pending,
        "urgentCount": urgent_count,
        "avgWaitHours": avg_wait_hours,
        "paymentInitiatedCount": payment_initiated_count,
    }

    return render(request, "admin/agents/pending_registrations.html", context)


from django.views.decorators.csrf import csrf_protect


@require_POST
@csrf_protect
def admin_verify_pending_payment(request):
    """
    Admin endpoint to manually verify a pending payment via Razorpay API.
    If payment was captured/authorized, triggers the full activation flow:
    subscription update, agent activation, user creation, invoice generation, welcome email.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = request.POST

    agent_id = data.get("agent_id")
    if not agent_id:
        return JsonResponse(
            {"success": False, "message": "Agent ID is required."}, status=400
        )

    from apps.agents.models import Agent, AgentSubscription

    agent = Agent.objects.filter(pk=agent_id).first()
    if not agent:
        return JsonResponse(
            {"success": False, "message": "Agent not found."}, status=404
        )

    from apps.agents.models import Invoice

    # Check for pending/failed subscription with razorpay_order_id
    subscription = (
        AgentSubscription.objects.filter(
            agent=agent,
            payment_status__in=["pending", "failed"],
        )
        .exclude(razorpay_order_id__isnull=True)
        .exclude(razorpay_order_id="")
        .order_by("-created_at")
        .first()
    )

    # A paid invoice no longer short-circuits: an already-active agent can have
    # a paid upgrade / renewal order whose callback and webhook were both lost.
    if (
        not subscription
        and Invoice.objects.filter(
            agent_email=agent.email, payment_status="paid"
        ).exists()
    ):
        return JsonResponse(
            {
                "success": True,
                "already_active": True,
                "message": f"Agent {agent.fullname} is already activated with a paid invoice.",
            }
        )

    if not subscription:
        return JsonResponse(
            {
                "success": False,
                "message": f"No pending payment found for {agent.fullname}. No Razorpay order was initiated.",
            },
            status=400,
        )

    # Use existing verify_and_activate_pending_payment function
    from apps.agents.views.registration import verify_and_activate_pending_payment

    try:
        result = verify_and_activate_pending_payment(agent, include_paid_agents=True)
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(
            f"Error during manual payment verification for {agent.email}: {e}"
        )
        return JsonResponse(
            {
                "success": False,
                "message": "An internal server error occurred while verifying the payment. Please try again later.",
            },
            status=500,
        )

    if result:
        agent.refresh_from_db()
        logger.info(
            f"[admin_verify_pending_payment] Admin #{admin_id} successfully verified payment for agent {agent.email} (ID: {agent.id})"
        )
        from apps.admin_panel.models import AdminActivityLog

        AdminActivityLog.log(
            "Verified pending payment",
            "Agent",
            agent.pk,
            details=f"order={subscription.razorpay_order_id} status={agent.status}",
            request=request,
        )
        return JsonResponse(
            {
                "success": True,
                "message": (
                    f"Payment verified successfully for {agent.fullname}! Agent moved to Pending Approval queue."
                    if agent.status == "pending_approval"
                    else f"Payment verified successfully for {agent.fullname}! Plan updated (status: {agent.status})."
                ),
                "agent_status": agent.status,
            }
        )
    else:
        logger.info(
            f"[admin_verify_pending_payment] Admin #{admin_id} attempted verification for agent {agent.email} (ID: {agent.id}) — payment NOT found on Razorpay"
        )
        from apps.agents.services.account_auth import agent_has_completed_payment

        if agent_has_completed_payment(agent):
            return JsonResponse(
                {
                    "success": True,
                    "already_active": True,
                    "message": f"Agent {agent.fullname} is already activated. The newer order {subscription.razorpay_order_id} has no payment on Razorpay.",
                }
            )
        return JsonResponse(
            {
                "success": False,
                "message": f"Payment NOT received from Razorpay for order {subscription.razorpay_order_id}. The user may not have completed the payment on the Razorpay checkout page.",
            },
            status=400,
        )


@never_cache
def admin_edit_profile(request, id):
    """Full profile editor under /admin/agents/<id>/edit-profile/."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    from apps.agents.models import Agent
    from apps.agents.views.dashboard import render_edit_profile

    agent = Agent.objects.filter(id=id).first()
    if not agent:
        messages.error(request, "Agent not found.")
        return redirect("admin_agents")
    return render_edit_profile(request, agent, is_admin_view=True)


@require_POST
@never_cache
def admin_full_update_profile(request, id):
    """POST target for the admin full profile editor. Distinct from manage-stats update_profile."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse(
            {"status": "error", "message": "Authentication required"}, status=401
        )

    from apps.agents.models import Agent
    from apps.agents.views.dashboard import apply_profile_update

    agent = Agent.objects.filter(id=id).first()
    if not agent:
        return JsonResponse(
            {"status": "error", "message": "Agent not found"}, status=404
        )
    return apply_profile_update(request, agent, is_admin_edit=True)
