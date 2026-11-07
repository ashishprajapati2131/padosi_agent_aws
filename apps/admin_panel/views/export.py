"""
apps/admin_panel/views/export.py

Export Center — PHASE EXPORT_CENTER.MERGE
Source: django/padosi_agent/apps/admin_panel/views/export.py

Adaptations from source:
  - Removed @admin_login_required decorator (absent in target); replaced with
    manual _get_admin_from_session() guard matching target project pattern.
  - Replaced source model imports (apps.agents.models) with target equivalents
    (apps.admin_panel.models) which expose the same managed=False tables.
  - All SQL queries, CSV structure, and business logic are preserved identically.
"""

from apps.admin_panel.services.spreadsheet_safety import streaming_csv_response

from django.http import StreamingHttpResponse
from django.shortcuts import redirect, render
from django.utils.timezone import now

from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.admin_panel.models import Agent, AgentSubscription, AgentReview
from apps.admin_panel.models.contact_submission import ContactSubmission
from apps.admin_panel.selectors.export import (
    count_table,
    fetch_agent_export_rows,
    fetch_lead_export_rows,
    fetch_pending_export_rows,
    fetch_review_export_rows,
    fetch_subscription_export_rows,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _csv_response(filename: str, header: list, rows) -> StreamingHttpResponse:
    """Streamed, formula-safe CSV download (rows may be any iterable)."""
    return streaming_csv_response(filename, header, rows)


def _today() -> str:
    return now().strftime("%Y-%m-%d")


# ─── Index ───────────────────────────────────────────────────────────────────


def index(request):
    """Export Center landing page – mirrors AdminExportController::index."""
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    counts = {
        "agents": Agent.objects.count(),
        "leads": count_table("agent_leads"),
        "contacts": ContactSubmission.objects.count(),
        "subscriptions": AgentSubscription.objects.count(),
        "reviews": AgentReview.objects.count(),
    }
    return render(request, "admin/export_center.html", {"counts": counts})


# ─── Agents CSV ──────────────────────────────────────────────────────────────


def export_agents(request):
    """Export agents with profile + subscription info as CSV."""
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    status_filter = request.GET.get("status", "all")
    if status_filter == "All Status":
        status_filter = "all"

    rows_raw = fetch_agent_export_rows(status_filter)

    header = [
        "ID",
        "Full Name",
        "Display Name",
        "Email",
        "Mobile",
        "Status",
        "Agency",
        "Address",
        "User Types",
        "Experience",
        "Plan",
        "Plan Expires",
        "Joined",
    ]
    rows = (
        [
            r[0],
            r[1] or "",
            r[2] or "",
            r[3] or "",
            r[4] or "",
            r[5] or "",
            r[6] or "",
            r[7] or "",
            r[8] or "",
            r[9] or "",
            r[10] or "",
            str(r[11]) if r[11] else "",
            str(r[12]) if r[12] else "",
        ]
        for r in rows_raw
    )
    return _csv_response(f"agents_{status_filter}_{_today()}.csv", header, rows)


# ─── Leads CSV ───────────────────────────────────────────────────────────────


def export_leads(request):
    """Export agent leads as CSV.
    Real agent_leads columns: customer_name, customer_email, customer_mobile,
    customer_pincode, interaction_type, lead_status, service_type,
    insurance_type, insurance_company, enquiry_requirements, source_page.
    """
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    type_filter = request.GET.get("type", "all")

    rows_raw = fetch_lead_export_rows(type_filter)

    header = [
        "ID",
        "Agent Name",
        "Agent Email",
        "Lead Type",
        "Customer Name",
        "Customer Mobile",
        "Customer Email",
        "Customer Pincode",
        "Service Type",
        "Insurance Type",
        "Status",
        "Date",
    ]
    rows = (
        [
            r[0],
            r[1] or "",
            r[2] or "",
            r[3] or "",
            r[4] or "",
            r[5] or "",
            r[6] or "",
            r[7] or "",
            r[8] or "",
            r[9] or "",
            r[10] or "",
            str(r[11]) if r[11] else "",
        ]
        for r in rows_raw
    )
    return _csv_response(f"leads_{type_filter}_{_today()}.csv", header, rows)


# ─── Contacts CSV ────────────────────────────────────────────────────────────


def export_contacts(request):
    """Export contact submissions as CSV."""
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    qs = ContactSubmission.objects.order_by("-created_at")
    header = ["ID", "Name", "Email", "Phone", "Subject", "Message", "Status", "Date"]
    rows = (
        [
            r.id,
            r.name or "",
            r.email or "",
            r.mobile or "",
            r.subject or "",
            r.message or "",
            r.status or "",
            str(r.created_at) if r.created_at else "",
        ]
        for r in qs
    )
    return _csv_response(f"contacts_{_today()}.csv", header, rows)


# ─── Subscriptions CSV ───────────────────────────────────────────────────────


def export_subscriptions(request):
    """Export subscription history as CSV."""
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    rows_raw = fetch_subscription_export_rows()

    header = [
        "ID",
        "Agent Name",
        "Agent Email",
        "Plan",
        "Amount (Rs.)",
        "Payment Status",
        "Starts At",
        "Expires At",
        "Created At",
    ]
    rows = (
        [
            r[0],
            r[1] or "",
            r[2] or "",
            r[3] or "",
            r[4] or "",
            r[5] or "",
            str(r[6]) if r[6] else "",
            str(r[7]) if r[7] else "",
            str(r[8]) if r[8] else "",
        ]
        for r in rows_raw
    )
    return _csv_response(f"subscriptions_{_today()}.csv", header, rows)


# ─── Reviews CSV ─────────────────────────────────────────────────────────────


def export_reviews(request):
    """Export agent reviews as CSV."""
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    rows_raw = fetch_review_export_rows()

    header = ["ID", "Agent", "Reviewer Name", "Rating", "Review", "Approved", "Date"]
    rows = (
        [
            r[0],
            r[1] or "",
            r[2] or "",
            r[3] or "",
            r[4] or "",
            "Yes" if r[5] else "No",
            str(r[6]) if r[6] else "",
        ]
        for r in rows_raw
    )
    return _csv_response(f"reviews_{_today()}.csv", header, rows)


# ─── Pending Registrations CSV ───────────────────────────────────────────────


def export_pending(request):
    """Export incomplete/pending agents as CSV."""
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    search = request.GET.get("search", "")
    event_filter = request.GET.get("event_id", "All Events")

    from apps.admin_panel.views.agents import _event_filter_sql

    event_sql, event_params = _event_filter_sql(event_filter)
    rows_raw = fetch_pending_export_rows(search, event_sql, event_params)

    header = [
        "ID",
        "Full Name",
        "Display Name",
        "Email",
        "Mobile",
        "Status",
        "Reg. Step",
        "Selected Plan",
        "Amount (Rs.)",
        "Payment Status",
        "Location",
        "Waiting (Hours)",
        "Registered At",
    ]
    rows = (
        [
            r[0],
            r[1] or "",
            r[2] or "",
            r[3] or "",
            r[4] or "",
            r[5] or "",
            r[6] or "",
            r[7] or "Not Selected",
            r[8] or "0",
            r[9] or "",
            r[10] or "",
            r[11] or 0,
            str(r[12]) if r[12] else "",
        ]
        for r in rows_raw
    )
    return _csv_response(f"pending_registrations_{_today()}.csv", header, rows)
