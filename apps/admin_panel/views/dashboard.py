"""
apps/admin_panel/views/dashboard.py

Phase 2 — Admin Dashboard Backend

Laravel source: app/Http/Controllers/Admin/AdminDashboardController.php
Migration rules: padosi_migration_plan.md, PROJECT_STRUCTURE.md

Conversion notes:
  - All DB queries are raw SQL via django.db.connection (no ORM models exist yet for
    agents/subscriptions/leads/reviews — models are managed=False placeholders for Phase 3+).
  - Authentication: uses the custom session system (user_sessions + user_session_data tables).
    No Django auth, no django_session. Session token validated via cookie on every protected view.
  - Period filter (?period=3|6|12) preserved exactly as in Laravel.
  - Plan breakdown JSON-decode logic mirrors PHP json_decode() fallback.
  - All MySQL-specific SQL (DATE_FORMAT, DATE_SUB, LAST_DAY, UTC_TIMESTAMP, INTERVAL) is
    preserved as-is — the project uses MySQL (see settings.py).
  - Error handling wraps all DB operations, returning safe zero-defaults on failure —
    matching Laravel's try/catch pattern exactly.
"""

import logging
import secrets
from datetime import datetime, timedelta

from password_hashing import check_password_hash

from django.conf import settings
from django.contrib.auth import logout as django_logout
from django.core.cache import cache
from django.db import connection
from django.shortcuts import render, redirect


logger = logging.getLogger(__name__)

# Session helpers live in apps/admin_panel/auth.py; re-exported here because many
# modules (and tests' patch targets) still use apps.admin_panel.views.dashboard.<name>.
from apps.admin_panel.auth import (  # noqa: E402,F401
    ADMIN_SESSION_COOKIE,
    ADMIN_SESSION_DAYS,
    _admin_cookie_secure,
    _get_admin_from_session,
    _resolve_admin_from_session,
    clear_admin_session,
    invalidate_admin_session_token,
)


def _record_failed_admin_login(request, email):
    """
    Log failed administrative logins to SecurityThreatLog.
    If an IP registers >= 5 failures in an hour, add to BlockedIp.
    """
    # Same trusted-proxy IP rule as the WAF: a raw X-Forwarded-For value let an
    # attacker get any IP (e.g. the real admin's) auto-blocked site-wide.
    from apps.admin_panel.middleware import ThreatMonitorMiddleware
    ip = ThreatMonitorMiddleware.get_client_ip(request)

    try:
        from apps.admin_panel.models.admin_auth import SecurityThreatLog
        from apps.agents.models import BlockedIp
        import json
        
        SecurityThreatLog.objects.create(
            ip_address=ip,
            event_type='Failed Admin Login',
            url=request.build_absolute_uri(),
            payload=json.dumps({'email': email}),
            user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:255]
        )
        
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_failures = SecurityThreatLog.objects.filter(
            ip_address=ip,
            event_type='Failed Admin Login',
            created_at__gte=one_hour_ago
        ).count()
        
        if recent_failures >= 5:
            BlockedIp.objects.get_or_create(
                ip_address=ip,
                defaults={'reason': 'Auto-blocked due to recurring failed admin login attempts (Potential Brute Force).'}
            )
            logger.warning(f"Admin login brute force detected. IP blocked: {ip}")
    except Exception as e:
        logger.error(f"Error logging failed admin login threat log: {e}")


# ---------------------------------------------------------------------------
# Auth Views  (login / logout)  — preserved from Phase 1 stubs
# ---------------------------------------------------------------------------

def _mask_email(email: str) -> str:
    """Mask email for display, e.g. admin@padosiagent.com -> a***n@padosiagent.com"""
    if not email or "@" not in email:
        return email or ""
    try:
        user_part, domain_part = email.split("@", 1)
        if len(user_part) <= 2:
            masked_user = user_part[0] + "*"
        else:
            masked_user = user_part[0] + "*" * (len(user_part) - 2) + user_part[-1]
        return f"{masked_user}@{domain_part}"
    except Exception:
        return email


def _issue_admin_session(request, admin_db_id, email):
    """
    Issue an authenticated admin session and set the session cookie.
    """
    # Agent Django sessions and admin cookie sessions must not coexist.
    invalidate_admin_session_token(request.COOKIES.get(ADMIN_SESSION_COOKIE))
    django_logout(request)

    token = secrets.token_hex(32)
    now_curr = datetime.now()
    expires_at = now_curr + timedelta(days=ADMIN_SESSION_DAYS)
    from apps.admin_panel.middleware import ThreatMonitorMiddleware
    ip_address = (ThreatMonitorMiddleware.get_client_ip(request) or request.META.get("REMOTE_ADDR") or "")[:45]
    user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:255]

    try:
        with connection.cursor() as cursor:
            # Insert into user_sessions with fallback for schema variations
            try:
                cursor.execute(
                    """
                    INSERT INTO user_sessions
                        (session_token, admin_id, agent_id, distributor_id,
                         ip_address, user_agent, last_activity,
                         expires_at, created_at, updated_at)
                    VALUES
                        (%s, %s, NULL, NULL, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        token, admin_db_id, ip_address, user_agent,
                        now_curr, expires_at, now_curr, now_curr,
                    ],
                )
            except Exception:
                cursor.execute(
                    """
                    INSERT INTO user_sessions
                        (session_token, ip_address, user_agent, last_activity,
                         expires_at, created_at, updated_at)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        token, ip_address, user_agent,
                        now_curr, expires_at, now_curr, now_curr,
                    ],
                )
            session_id = cursor.lastrowid

            cursor.execute(
                """
                INSERT INTO user_session_data
                    (session_id, data_key, data_value, created_at, updated_at)
                VALUES
                    (%s, %s, %s, %s, %s)
                """,
                [session_id, "admin_id", str(admin_db_id), now_curr, now_curr],
            )
    except Exception as exc:
        logger.error("Session creation error: %s", exc)
        return render(request, "admin/login.html", {
            "error": "Could not create session. Please try again.",
            "old_email": email,
        })

    response = redirect("admin_dashboard")
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        token,
        max_age=ADMIN_SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="Lax",
        secure=_admin_cookie_secure(),
    )
    return response


def show_login_form(request):
    """
    Display the admin login page.
    Laravel: AdminAuthController@showLoginForm  →  GET /admin/login
    """
    return render(request, "admin/login.html")


ADMIN_LOGIN_MAX_FAILS = 10
ADMIN_LOGIN_LOCK_SECONDS = 15 * 60
_DUMMY_ADMIN_HASH = None


def _dummy_admin_hash():
    global _DUMMY_ADMIN_HASH
    if _DUMMY_ADMIN_HASH is None:
        from password_hashing import hash_password
        _DUMMY_ADMIN_HASH = hash_password(secrets.token_hex(16))
    return _DUMMY_ADMIN_HASH


def _count_failed_login(fail_key):
    # get+set (not incr): FileBasedCache.incr resets the timeout to the cache default.
    cache.set(fail_key, (cache.get(fail_key) or 0) + 1, timeout=ADMIN_LOGIN_LOCK_SECONDS)


def admin_login(request):
    """
    Handle admin login POST (both credential check and MFA verification).

    Laravel source: AdminAuthController@login  →  POST /admin/login
    Django route:   POST /admin/login/post/     →  name='admin_login_post'
    """
    if request.method != "POST":
        return render(request, "admin/login.html")

    # --- 0. Handle MFA Verification Submission ---
    mfa_ticket = request.POST.get("mfa_ticket")
    if mfa_ticket:
        session_data = cache.get(f"admin_mfa_{mfa_ticket}")
        if not session_data:
            return render(request, "admin/login.html", {
                "error": "Verification code has expired. Please log in again.",
            })

        otp = request.POST.get("otp", "").strip()
        attempts = session_data.get("attempts", 0) + 1
        session_data["attempts"] = attempts

        if attempts > 5:
            cache.delete(f"admin_mfa_{mfa_ticket}")
            return render(request, "admin/login.html", {
                "error": "Too many failed attempts. Please log in again.",
            })

        if not otp or otp != session_data.get("otp"):
            cache.set(f"admin_mfa_{mfa_ticket}", session_data, timeout=300)
            return render(request, "admin/login.html", {
                "mfa_required": True,
                "mfa_ticket": mfa_ticket,
                "masked_email": _mask_email(session_data.get("email", "")),
                "error": f"Invalid verification code. ({5 - attempts} attempts remaining)",
            })

        cache.delete(f"admin_mfa_{mfa_ticket}")
        return _issue_admin_session(request, session_data["admin_id"], session_data["email"])

    # --- 1. Read credentials ---
    email    = request.POST.get("email",    "").strip()
    password = request.POST.get("password", "")

    if not email or not password:
        return render(request, "admin/login.html", {
            "error":     "Email and password are required.",
            "old_email": email,
        })

    # Per-account lock on top of the per-IP block: stops slow brute force from many IPs.
    fail_key = f"admin_login_fail_{email.lower()}"
    if (cache.get(fail_key) or 0) >= ADMIN_LOGIN_MAX_FAILS:
        return render(request, "admin/login.html", {
            "error":     "Too many failed attempts for this account. Try again in 15 minutes.",
            "old_email": email,
        })

    # --- 2. Look up admin by email ---
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, password FROM admins WHERE email = %s LIMIT 1",
                [email],
            )
            row = cursor.fetchone()
    except Exception as exc:
        logger.error("Login DB lookup error: %s", exc)
        return render(request, "admin/login.html", {
            "error":     "A database error occurred. Please try again.",
            "old_email": email,
        })

    if not row:
        # Same bcrypt cost as a real account, so response time doesn't reveal which emails exist.
        check_password_hash(password, _dummy_admin_hash())
        _count_failed_login(fail_key)
        _record_failed_admin_login(request, email)
        return render(request, "admin/login.html", {
            "error":     "Invalid email or password.",
            "old_email": email,
        })

    admin_db_id, stored_hash = row

    # --- 3. Verify password (bcrypt, same helper as every other login) ---
    try:
        password_valid = check_password_hash(password, stored_hash)
    except Exception as exc:
        logger.error("bcrypt verification error: %s", exc)
        return render(request, "admin/login.html", {
            "error":     "Authentication error. Please try again.",
            "old_email": email,
        })

    if not password_valid:
        _count_failed_login(fail_key)
        _record_failed_admin_login(request, email)
        return render(request, "admin/login.html", {
            "error":     "Invalid email or password.",
            "old_email": email,
        })

    cache.delete(fail_key)

    # --- 4. Two-Factor Authentication (MFA) Gate ---
    admin_mfa_enabled = getattr(settings, "ADMIN_MFA_ENABLED", False)
    if admin_mfa_enabled:
        from apps.admin_panel.services.brevo import send_otp_email

        otp = f"{secrets.randbelow(900000) + 100000}"
        new_mfa_ticket = secrets.token_urlsafe(32)
        cache.set(
            f"admin_mfa_{new_mfa_ticket}",
            {
                "admin_id": admin_db_id,
                "email": email,
                "otp": otp,
                "attempts": 0,
            },
            timeout=300,
        )

        try:
            send_otp_email(to_email=email, to_name="Administrator", otp_code=otp)
        except Exception as e:
            logger.error("Failed to send Admin MFA OTP email: %s", e)

        if settings.DEBUG:
            logger.info("[ADMIN MFA] Security code for %s: %s", email, otp)

        return render(request, "admin/login.html", {
            "mfa_required": True,
            "mfa_ticket": new_mfa_ticket,
            "masked_email": _mask_email(email),
            "info": "A 6-digit two-factor verification code has been sent to your email.",
        })

    return _issue_admin_session(request, admin_db_id, email)


def admin_logout(request):
    """
    Handle admin logout.
    Ignores cross-site GET requests (e.g. <img src="/admin/logout/">) to prevent
    forced session termination.
    """
    from apps.agents.views.auth import _is_cross_site_get
    if _is_cross_site_get(request):
        return redirect("admin_dashboard")

    django_logout(request)
    from apps.home.services.portal_messages import PORTAL_ADMIN, portal_success
    portal_success(request, "You have been logged out successfully.", PORTAL_ADMIN)
    response = redirect("admin_login")
    return clear_admin_session(request, response)


# Dashboard statistics queries live in selectors/dashboard.py; re-exported here
# because tests import them from this module.
from apps.admin_panel.selectors.dashboard import (  # noqa: E402,F401
    _fetch_agent_counts,
    _fetch_city_data,
    _fetch_engagement_stats,
    _fetch_mom_data,
    _fetch_plan_breakdown,
    _fetch_recent_leads,
    _fetch_renewal_stats,
    _fetch_top_agents_by_leads,
)


# ---------------------------------------------------------------------------
# Dashboard View
# ---------------------------------------------------------------------------

def admin_dashboard(request):
    """
    Admin dashboard view — aggregates all statistics and renders the dashboard.

    Laravel source:  AdminDashboardController@index  →  GET /admin/dashboard
    Django route:    GET  /admin/dashboard/           →  name='admin_dashboard'

    Session protection:
      Reads session_token cookie → validates against user_sessions / user_session_data.
      If invalid or expired → redirects to admin login.
      (Laravel equivalent: Route::middleware(['admin']) wrapping all admin routes)

    Period filter:
      ?period=3|6|12  (default: 12)
      Controls the MoM registration chart range, exactly as in Laravel.

    Context variables sent to template (identical names to Laravel's compact() call):
      period_months, total_agents, active_count, active_percent,
      new_this_month, growth_percent, distributors, retention_rate,
      upgrade_rate, page_views, total_leads, plan_breakdown,
      starter_count, prof_count, total_subs,
      mom_data, city_data, renewal_stats,
      new_leads_today, pending_reviews, total_reviews,
      pending_contacts, profile_views, top_agents_by_leads, recent_leads
    """
    # --- Session Authentication ---
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    # --- Period Filter (Laravel: $periodMonths = in_array(...) ? ... : 12) ---
    try:
        period_months = int(request.GET.get("period", 12))
        if period_months not in (3, 6, 12):
            period_months = 12
    except (ValueError, TypeError):
        period_months = 12

    # --- Default Safe Values (mirrors Laravel catch block, lines 137–160) ---
    context = {
        "period_months":      period_months,
        "total_agents":       0,
        "active_count":       0,
        "active_percent":     0,
        "new_this_month":     0,
        "growth_percent":     0,
        "distributors":       0,
        "retention_rate":     0,
        "plan_breakdown":     {},
        "total_subs":         0,
        "prof_count":         0,
        "starter_count":      0,
        "upgrade_rate":       0,
        "avg_leads_per_agent": 0,
        "page_views":         0,
        "total_leads":        0,
        "new_leads_today":    0,
        "pending_reviews":    0,
        "total_reviews":      0,
        "pending_contacts":   0,
        "profile_views":      0,
        "top_agents_by_leads": [],
        "recent_leads":       [],
        "mom_data":           [],
        "city_data":          [],
        "renewal_stats":      {"expired": 0, "next_30": 0, "next_60": 0, "next_90": 0},
        # JSON-serialised for Chart.js (mirrors @json() in Blade)
        "mom_labels":    [],
        "mom_totals":    [],
        "plan_keys":     [],
        "plan_values":   [],
    }

    # ~20 aggregate queries; the numbers don't need to be live to the second.
    stats_cache_key = f"admin_dashboard_stats_v1_{period_months}"
    cached_stats = cache.get(stats_cache_key)
    if cached_stats is not None:
        context.update(cached_stats)
        return render(request, "admin/dashboard.html", context)

    try:
        # Agent counts
        agent_data = _fetch_agent_counts()
        context.update(agent_data)

        # Plan breakdown
        plan_data = _fetch_plan_breakdown()
        context.update(plan_data)

        # Engagement stats
        engagement_data = _fetch_engagement_stats()
        context.update(engagement_data)

        # Avg leads per agent — mirrors Blade: number_format($totalLeads / max(1, $totalAgents), 1)
        _ta = context.get("total_agents", 0) or 1
        context["avg_leads_per_agent"] = round(context.get("total_leads", 0) / _ta, 1)

        # Top agents by leads
        context["top_agents_by_leads"] = _fetch_top_agents_by_leads()

        # Recent leads
        context["recent_leads"] = _fetch_recent_leads()

        # Month-over-month chart data
        mom_data = _fetch_mom_data(period_months)
        context["mom_data"] = mom_data

        # City data
        context["city_data"] = _fetch_city_data()

        # Renewal stats
        context["renewal_stats"] = _fetch_renewal_stats()

        # --- JSON-safe chart data for Chart.js (mirrors @json() in Blade) ---
        context["mom_labels"] = [row["label"] for row in mom_data]
        context["mom_totals"] = [row["total"] for row in mom_data]
        context["plan_keys"]  = list(context["plan_breakdown"].keys())
        context["plan_values"] = list(context["plan_breakdown"].values())
        cache.set(stats_cache_key, {k: v for k, v in context.items() if k != "period_months"}, timeout=120)

    except Exception as exc:
        # Mirrors Laravel: Log::error("Dashboard Data Fetch Error: " . $e->getMessage())
        logger.error("Dashboard Data Fetch Error: %s", exc)
        # context already has safe defaults set above

    return render(request, "admin/dashboard.html", context)