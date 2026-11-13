"""Shared registration constants (states, segments, statuses) and small session/IP/redirect helpers."""

import logging
import json
import re
from django.urls import reverse
from apps.home.models import SiteSetting
from apps.agents.services.feature_unlock import PLAN_LABELS, paid_plan_label

# Same logger name as before the split, so log routing and assertLogs() are unchanged.
logger = logging.getLogger("apps.agents.views.registration")


# ─── Constants ──────────────────────────────────────────────────────────────────
OTP_EXPIRY_SECONDS = 600  # 10 minutes


ALL_INDIAN_STATES = [
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
    "Andaman and Nicobar Islands",
    "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Jammu and Kashmir",
    "Ladakh",
    "Lakshadweep",
    "Puducherry",
]


INSURANCE_SEGMENTS = [
    {"id": "health", "label": "Health", "icon": "fas fa-heartbeat"},
    {"id": "life", "label": "Life", "icon": "fas fa-user-shield"},
    {"id": "motor", "label": "Motor", "icon": "fas fa-car"},
    {"id": "sme", "label": "SME", "icon": "fas fa-building"},
]


ALLOWED_SEGMENT_IDS = frozenset(item["id"] for item in INSURANCE_SEGMENTS)


ALLOWED_INVESTMENT_TYPES = frozenset({"sip", "lumpsum", "elss"})


_RESERVED_PROFILE_SLUGS = frozenset(
    {
        "admin",
        "django-admin",
        "about",
        "contact",
        "terms",
        "privacy",
        "faq",
        "find-agents",
        "calculators",
        "calculator",
        "coming-soon",
        "lic-agent",
        "cancellation-refund-policy",
        "blacklisted-agents",
        "marketing",
        "media",
        "static",
        "agent-registration",
        "agent-register-step1",
        "agent-register-step2",
        "agent-login",
        "forgot-password",
        "reset-password",
        "agent-logout",
        "logout",
        "profile",
        "card",
        "review",
        "review-card",
        "join",
        "auth",
        "events",
        "chatbot-api",
        "championship",
        "insurance",
        "insurance-login",
        "api",
        "manifest.webmanifest",
        "sw.js",
        "offline.html",
        "sitemap.xml",
        "robots.txt",
    }
)


LANGUAGE_OPTIONS = [
    "Hindi",
    "English",
    "Gujarati",
    "Marathi",
    "Tamil",
    "Telugu",
    "Kannada",
    "Bengali",
    "Punjabi",
    "Malayalam",
    "Odia",
    "Urdu",
    "Assamese",
    "Rajasthani",
]


def _is_in_progress_razorpay_error(error):
    """Netbanking/UPI redirects fire payment.failed before the bank returns."""
    if not isinstance(error, dict):
        return False
    step = str(error.get("step") or "").strip().lower()
    reason = str(error.get("reason") or "").strip().lower()
    if step in (
        "payment_authentication",
        "payment_capture",
        "payment_redirect",
        "redirect",
    ):
        return True
    if reason in ("payment_pending", "payment_redirect"):
        return True
    return False


def _clear_checkout_session(request):
    """Forget the finished signup/checkout in this browser session."""
    for key in ("current_draft_id", "reg_step", "ref_code", "pending_checkout"):
        request.session.pop(key, None)


def _session_owns_agent(request, agent):
    """True when this browser session legitimately belongs to ``agent``.

    Payment endpoints must never log a session into an agent chosen by the
    request payload — only the agent this session started checkout for (or is
    already signed in as) may be logged in after payment verification.
    """
    if not agent or not getattr(agent, "pk", None):
        return False
    pending = request.session.get("pending_checkout") or {}
    candidates = (pending.get("agent_id"), request.session.get("agent_id"))
    if any(str(c) == str(agent.pk) for c in candidates if c):
        return True
    user = getattr(request, "user", None)
    return bool(
        user is not None
        and user.is_authenticated
        and agent.user_id
        and agent.user_id == user.pk
    )


def _is_plan_upgrade_payment(agent, order_id=None):
    """True when the agent already had a completed subscription before this order."""
    if not agent:
        return False
    from apps.agents.models import AgentSubscription

    qs = AgentSubscription.objects.filter(agent=agent, payment_status="completed")
    if order_id:
        qs = qs.exclude(razorpay_order_id=order_id)
    return qs.exists()


def _deactivate_superseded_subscriptions(agent, keep_subscription_id):
    """Keep only the latest paid subscription active after an upgrade."""
    if not agent or not keep_subscription_id:
        return
    from apps.agents.models import AgentSubscription

    AgentSubscription.objects.filter(
        agent=agent,
        status="active",
    ).exclude(pk=keep_subscription_id).update(status="inactive")


def _display_plan_name(agent, pricing_config):
    """Dashboard header plan label — checks active subscription selected_plan first to match admin listing, falling back to agent.plan_type slug."""
    from apps.agents.services.feature_unlock import normalize_plan_slug

    active_sub = getattr(agent, "activeSubscription", None)
    if not active_sub and hasattr(agent, "subscriptions"):
        try:
            active_sub = (
                agent.subscriptions.filter(status="active")
                .order_by("-starts_at", "-created_at", "-id")
                .first()
            ) or agent.subscriptions.order_by("-id").first()
        except Exception:
            active_sub = None

    if active_sub and active_sub.selected_plan:
        raw_plan = str(active_sub.selected_plan).strip()
        try:
            decoded = json.loads(raw_plan)
            if isinstance(decoded, dict) and decoded.get("name"):
                raw_plan = str(decoded["name"]).strip()
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        if raw_plan:
            label = paid_plan_label(raw_plan)
            if label in (PLAN_LABELS["starter"], PLAN_LABELS["professional"]):
                return label
            return raw_plan

    slug = normalize_plan_slug(getattr(agent, "plan_type", "") or "")
    if slug == "free_trial":
        return "Free Trial"
    if slug == "exclusive":
        from apps.home.models import SiteSetting

        ex_cfg = SiteSetting.get_value("exclusive_plan_config") or {}
        return ex_cfg.get("name") or "Exclusive Plan"

    return paid_plan_label(slug or "starter")


def _razorpay_callback_payload(request):
    data = {}
    if request.method == "POST":
        content_type = (request.content_type or "").lower()
        if "json" in content_type:
            try:
                data = json.loads(request.body or "{}")
            except json.JSONDecodeError:
                data = request.POST.dict()
        else:
            data = request.POST.dict()
    else:
        data = request.GET.dict()
    pending = request.session.get("pending_checkout") or {}
    return {
        "razorpay_payment_id": data.get("razorpay_payment_id"),
        "razorpay_order_id": data.get("razorpay_order_id") or pending.get("order_id"),
        "razorpay_signature": data.get("razorpay_signature"),
        # Never trust a client-supplied agent_id: it selects whose session gets
        # logged in. Only the server-side checkout session may name the agent.
        "agent_id": pending.get("agent_id"),
        "plan_type": data.get("plan_type") or pending.get("plan_type"),
        "plan_name": data.get("plan_name") or pending.get("plan_name"),
        "error": data.get("error")
        or {
            "code": data.get("error[code]") or data.get("error_code"),
            "description": data.get("error[description]")
            or data.get("error_description"),
            "step": data.get("error[step]"),
            "reason": data.get("error[reason]"),
        },
    }


def _get_client_ip(request):
    # Trusted-proxy rule (CLAUDE.md invariant #4): the first X-Forwarded-For
    # hop is client-controlled, so the step-1 rate limit could be bypassed or
    # aimed at someone else's IP.
    from apps.admin_panel.middleware import ThreatMonitorMiddleware

    return ThreatMonitorMiddleware.get_client_ip(request) or request.META.get(
        "REMOTE_ADDR", ""
    )


# ─── Helper ─────────────────────────────────────────────────────────────────────


REG_FORM_SHOWN_AT_KEY = "reg_form_shown_at"


def _int_or_zero(value):
    try:
        digits = re.sub(r"\D", "", str(value or ""))
        return int(digits) if digits else 0
    except (TypeError, ValueError):
        return 0


def _public_profile_path(agent):
    slug = ""
    try:
        profile = getattr(agent, "profile", None)
        slug = (profile.slug or "") if profile else ""
    except Exception:
        slug = ""
    if not slug:
        slug = getattr(agent, "agent_slug", "") or ""
    if not slug:
        return reverse("agents:agent_dashboard")

    return f"/{slug}/"


def _post_payment_redirect_url(request, agent=None):
    """First-time website signup lands on edit profile; upgrades stay on dashboard."""
    from apps.distributors.views.dashboard import is_distributor

    try:
        if request.user.is_authenticated and is_distributor(request.user):
            return reverse("distributors:agents_index")
    except Exception:
        pass
    if request.session.get("app_upgrade_handoff_plan"):
        return reverse("agents:agent_dashboard") + "?upgrade_success=1"
    if agent is not None and getattr(agent, "pk", None):
        from apps.agents.models import AgentSubscription

        # Renewal / repeat payment: an earlier paid order exists.
        if (
            AgentSubscription.objects.filter(
                agent=agent, payment_status="completed"
            ).count()
            > 1
        ):
            return reverse("agents:agent_dashboard")
    return reverse("agents:agent_edit_profile") + "?welcome=1"


def _activation_success_payload(
    request, agent, message="Payment successful and account activated."
):
    redirect_url = _post_payment_redirect_url(request, agent)
    profile_path = _public_profile_path(agent)
    return {
        "success": True,
        "message": message,
        "redirect_url": redirect_url,
        "agent_name": (getattr(agent, "fullname", "") or "").strip(),
        "profile_url": request.build_absolute_uri(profile_path),
    }


# Agent statuses a registration may still (re)start from. Any later status
# (awaiting approval, active, suspended...) is never reset by a checkout.
REGISTRATION_STAGE_STATUSES = (
    "incomplete",
    "pending_payment",
    "rejected",
    "event_challenge",
)


# Step 1 needs no login, so it reuses only these. A Paldi challenger
# (event_challenge) continues from their own logged-in session instead.
STEP1_REUSABLE_STATUSES = ("incomplete", "pending_payment", "rejected")


def create_or_link_django_user(agent, plain_password=None):
    from apps.agents.services.account_auth import (
        create_or_link_django_user as _create_or_link,
    )

    return _create_or_link(agent, plain_password=plain_password)
