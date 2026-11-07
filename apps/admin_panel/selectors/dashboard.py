"""Read-only statistics queries for the admin dashboard (views/dashboard.py)."""

import json
import logging
from datetime import datetime, date, timedelta, timezone

from django.db import connection

logger = logging.getLogger(__name__)


def _fetch_agent_counts():
    """
    Fetch total agents, active count, active percent, new this month,
    last month count, growth percent, and distributors count.

    Laravel equivalent (lines 17–35 of AdminDashboardController):
        $totalAgents    = DB::table('agents')->count();
        $activeCount    = DB::table('agents')->where('status', 'active')->count();
        $activePercent  = $totalAgents > 0 ? round(($activeCount / $totalAgents) * 100) : 0;
        $newThisMonth   = DB::table('agents')->whereMonth(...)->whereYear(...)->count();
        $lastMonthCount = DB::table('agents')->whereMonth(sub1)->whereYear(...)->count();
        $growthPercent  = ...
        $distributors   = DB::table('agents')->where('user_types', 'LIKE', '%distributor%')...->count();
    """
    now = datetime.now(timezone.utc)
    this_month = now.month
    this_year = now.year

    # Previous month
    first_of_this_month = now.replace(day=1)
    last_month_dt = first_of_this_month - timedelta(days=1)
    last_month = last_month_dt.month
    last_month_year = last_month_dt.year

    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM agents")
        total_agents = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM agents WHERE status = 'active'")
        active_count = cursor.fetchone()[0]

        active_percent = round((active_count / total_agents) * 100) if total_agents > 0 else 0

        cursor.execute(
            "SELECT COUNT(*) FROM agents WHERE MONTH(created_at) = %s AND YEAR(created_at) = %s",
            [this_month, this_year],
        )
        new_this_month = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM agents WHERE MONTH(created_at) = %s AND YEAR(created_at) = %s",
            [last_month, last_month_year],
        )
        last_month_count = cursor.fetchone()[0]

        growth_percent = (
            round(((new_this_month - last_month_count) / last_month_count) * 100)
            if last_month_count > 0
            else 0
        )

        cursor.execute(
            """
            SELECT COUNT(*) FROM agents
            WHERE user_types LIKE %s OR profession LIKE %s
            """,
            ["%distributor%", "%distributor%"],
        )
        distributors = cursor.fetchone()[0]

    return {
        "total_agents": total_agents,
        "active_count": active_count,
        "active_percent": active_percent,
        "new_this_month": new_this_month,
        "last_month_count": last_month_count,
        "growth_percent": growth_percent,
        "distributors": distributors,
        "retention_rate": active_percent,  # Same as activePercent in Laravel
    }


def _fetch_plan_breakdown():
    """
    Fetch subscription plan distribution and compute upgrade rate.

    Laravel equivalent (lines 39–61 of AdminDashboardController):
        $rawPlans = DB::table('agent_subscriptions')
            ->select('selected_plan', DB::raw('count(*) as c'))
            ->groupBy('selected_plan')
            ->pluck('c', 'selected_plan')
            ->toArray();

    The selected_plan column may contain:
      - A plain string:  "Professional's Plan"
      - A JSON string:   '{"name": "Professional\'s Plan", "type": "professional"}'
    Both cases are handled by trying json.loads() first, then falling back to
    the raw string — exactly as PHP json_decode() + json_last_error() does.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT selected_plan, COUNT(*) as c
            FROM agent_subscriptions
            GROUP BY selected_plan
            """
        )
        raw_rows = cursor.fetchall()

    plan_breakdown = {}
    for plan_key, count in raw_rows:
        plan_key = (plan_key or "").strip()
        name = plan_key
        if plan_key.startswith("{"):
            try:
                decoded = json.loads(plan_key)
                name = decoded.get("name") or decoded.get("type") or "Other"
            except (json.JSONDecodeError, ValueError):
                pass
        plan_breakdown[name] = plan_breakdown.get(name, 0) + count

    total_subs = sum(plan_breakdown.values())

    from apps.agents.services.feature_unlock import plan_slug_from_name

    prof_count = starter_count = 0
    for label, count in plan_breakdown.items():
        slug = plan_slug_from_name(label)
        if slug == 'professional':
            prof_count += count
        elif slug == 'starter':
            starter_count += count
    upgrade_rate = round((prof_count / total_subs) * 100) if total_subs > 0 else 0

    return {
        "plan_breakdown": plan_breakdown,
        "total_subs": total_subs,
        "prof_count": prof_count,
        "starter_count": starter_count,
        "upgrade_rate": upgrade_rate,
    }


def _fetch_engagement_stats():
    r"""
    Fetch page views, leads, reviews, contacts, and profile views.

    Laravel equivalent (lines 63–76 of AdminDashboardController):
        $pageViews     = DB::table('sessions')->count();
        $totalLeads    = DB::table('agent_leads')->count();
        $newLeadsToday = DB::table('agent_leads')->whereDate('created_at', today())->count();
        $pendingReviews= DB::table('agent_reviews')->where('is_approved', 0)->count();
        $totalReviews  = DB::table('agent_reviews')->count();
        $pendingContacts = DB::table('contact_submissions')->where('status', 'pending')->count();
        $profileViews  = 0;
        try { $profileViews = DB::table('agent_profile_views')->count(); } catch (\Exception $e) {}

    Note: In Laravel 'sessions' refers to the framework's session table.
    Here we use user_sessions (the custom session table already built in Phase 1).
    """
    today_str = date.today().isoformat()

    with connection.cursor() as cursor:
        # Page views → count from custom session table (equivalent to Laravel's sessions table)
        cursor.execute("SELECT COUNT(*) FROM user_sessions")
        page_views = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM agent_leads")
        total_leads = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM agent_leads WHERE DATE(created_at) = %s",
            [today_str],
        )
        new_leads_today = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM agent_reviews WHERE is_approved = 0")
        pending_reviews = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM agent_reviews")
        total_reviews = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM contact_submissions WHERE status = 'pending'"
        )
        pending_contacts = cursor.fetchone()[0]

    # profile_views: guarded separately — table may not exist yet
    profile_views = 0
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM agent_profile_views")
            profile_views = cursor.fetchone()[0]
    except Exception as exc:
        logger.debug("agent_profile_views not available: %s", exc)

    return {
        "page_views": page_views,
        "total_leads": total_leads,
        "new_leads_today": new_leads_today,
        "pending_reviews": pending_reviews,
        "total_reviews": total_reviews,
        "pending_contacts": pending_contacts,
        "profile_views": profile_views,
    }


def _fetch_top_agents_by_leads():
    """
    Fetch top 5 agents ranked by total lead count, with WhatsApp/call breakdown.

    Laravel equivalent (lines 79–92 of AdminDashboardController):
        $topAgentsByLeads = DB::table('agent_leads as l')
            ->leftJoin('agents as a', 'l.agent_id', '=', 'a.id')
            ->leftJoin('agent_profiles as ap', 'a.id', '=', 'ap.agent_id')
            ->select('a.id', 'a.fullname', 'ap.display_name',
                     DB::raw('COUNT(*) as lead_count'),
                     DB::raw("SUM(CASE WHEN l.interaction_type = 'whatsapp' THEN 1 ELSE 0 END) as whatsapp_count"),
                     DB::raw("SUM(CASE WHEN l.interaction_type = 'call' THEN 1 ELSE 0 END) as call_count"))
            ->groupBy('a.id', 'a.fullname', 'ap.display_name')
            ->orderByDesc('lead_count')
            ->limit(5)
            ->get();
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                a.id,
                a.fullname,
                ap.display_name,
                COUNT(*) AS lead_count,
                SUM(CASE WHEN l.interaction_type = 'whatsapp' THEN 1 ELSE 0 END) AS whatsapp_count,
                SUM(CASE WHEN l.interaction_type = 'call'     THEN 1 ELSE 0 END) AS call_count
            FROM agent_leads AS l
            LEFT JOIN agents AS a        ON l.agent_id = a.id
            LEFT JOIN agent_profiles AS ap ON a.id     = ap.agent_id
            GROUP BY a.id, a.fullname, ap.display_name
            ORDER BY lead_count DESC
            LIMIT 5
            """
        )
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

    # Return list of dicts so template accesses work identically to Laravel's $agent->lead_count
    return [dict(zip(columns, row)) for row in rows]


def _fetch_recent_leads():
    """
    Fetch last 5 leads with agent name joined.

    Laravel equivalent (lines 95–100 of AdminDashboardController):
        $recentLeads = DB::table('agent_leads as l')
            ->leftJoin('agents as a', 'l.agent_id', '=', 'a.id')
            ->select('l.*', 'a.fullname as agent_name')
            ->orderByDesc('l.created_at')
            ->limit(5)
            ->get();
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT l.*, a.fullname AS agent_name
            FROM agent_leads AS l
            LEFT JOIN agents AS a ON l.agent_id = a.id
            ORDER BY l.created_at DESC
            LIMIT 5
            """
        )
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

    return [dict(zip(columns, row)) for row in rows]


def _fetch_mom_data(period_months):
    """
    Fetch month-over-month registration counts for the chart.

    Laravel equivalent (lines 104–110 of AdminDashboardController):
        $momData = DB::select("
            SELECT DATE_FORMAT(created_at, '%b %y') as label, COUNT(*) as total
            FROM agents
            WHERE created_at >= DATE_SUB(LAST_DAY(UTC_TIMESTAMP()), INTERVAL ? MONTH)
            GROUP BY label, YEAR(created_at), MONTH(created_at)
            ORDER BY YEAR(created_at) ASC, MONTH(created_at) ASC
        ", [$periodMonths]);

    The raw MySQL SQL is preserved as-is (project uses MySQL).
    Returns list of dicts: [{'label': 'Jan 24', 'total': 12}, ...]
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DATE_FORMAT(created_at, '%%b %%y') AS label, COUNT(*) AS total
            FROM agents
            WHERE created_at >= DATE_SUB(LAST_DAY(%s), INTERVAL %s MONTH)
            GROUP BY label, YEAR(created_at), MONTH(created_at)
            ORDER BY YEAR(created_at) ASC, MONTH(created_at) ASC
            """,
            # created_at is naive IST (USE_TZ=False): compare with local now,
            # not UTC_TIMESTAMP() (5h30m behind).
            [datetime.now(), period_months],
        )
        rows = cursor.fetchall()

    return [{"label": row[0], "total": row[1]} for row in rows]


def _fetch_city_data():
    """
    Fetch top 8 cities by agent count.

    Laravel equivalent (lines 113–120 of AdminDashboardController):
        $cityData = DB::select("
            SELECT COALESCE(ap.address, 'Other') as label, COUNT(*) as total
            FROM agents a
            LEFT JOIN agent_profiles ap ON a.id = ap.agent_id
            GROUP BY label
            ORDER BY total DESC
            LIMIT 8
        ");
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COALESCE(ap.address, 'Other') AS label, COUNT(*) AS total
            FROM agents AS a
            LEFT JOIN agent_profiles AS ap ON a.id = ap.agent_id
            GROUP BY label
            ORDER BY total DESC
            LIMIT 8
            """
        )
        rows = cursor.fetchall()

    return [{"label": row[0], "total": row[1]} for row in rows]


def _fetch_renewal_stats():
    """
    Fetch subscription renewal alert counts (expired, due in 30/60/90 days).

    Laravel equivalent (lines 123–128 of AdminDashboardController):
        $renewalStats = collect(DB::select("SELECT
            SUM(CASE WHEN expires_at < UTC_TIMESTAMP() THEN 1 ELSE 0 END) as expired,
            SUM(CASE WHEN expires_at BETWEEN UTC_TIMESTAMP() AND DATE_ADD(UTC_TIMESTAMP(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) as next_30,
            SUM(CASE WHEN expires_at BETWEEN DATE_ADD(UTC_TIMESTAMP(), INTERVAL 31 DAY) AND DATE_ADD(UTC_TIMESTAMP(), INTERVAL 60 DAY) THEN 1 ELSE 0 END) as next_60,
            SUM(CASE WHEN expires_at BETWEEN DATE_ADD(UTC_TIMESTAMP(), INTERVAL 61 DAY) AND DATE_ADD(UTC_TIMESTAMP(), INTERVAL 90 DAY) THEN 1 ELSE 0 END) as next_90
          FROM agent_subscriptions"))->first();

    Returns dict with keys: expired, next_30, next_60, next_90.
    """
    # expires_at is naive IST (USE_TZ=False): compare with local now, not
    # UTC_TIMESTAMP() (5h30m behind). Python datetimes keep it DB-agnostic.
    now = datetime.now()
    day = timedelta(days=1)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                SUM(CASE WHEN expires_at < %s THEN 1 ELSE 0 END) AS expired,
                SUM(CASE WHEN expires_at BETWEEN %s AND %s THEN 1 ELSE 0 END) AS next_30,
                SUM(CASE WHEN expires_at BETWEEN %s AND %s THEN 1 ELSE 0 END) AS next_60,
                SUM(CASE WHEN expires_at BETWEEN %s AND %s THEN 1 ELSE 0 END) AS next_90
            FROM agent_subscriptions
            """,
            [now, now, now + 30 * day, now + 31 * day, now + 60 * day, now + 61 * day, now + 90 * day],
        )
        row = cursor.fetchone()

    if row:
        return {
            "expired": int(row[0] or 0),
            "next_30": int(row[1] or 0),
            "next_60": int(row[2] or 0),
            "next_90": int(row[3] or 0),
        }
    return {"expired": 0, "next_30": 0, "next_60": 0, "next_90": 0}
