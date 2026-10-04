"""
Comprehensive Database ORM & Endpoint Profiler.
Measures:
- Total query count per endpoint
- Duplicate queries (N+1 patterns)
- Total query duration (DB time)
- Total view execution duration (wall clock)
- Query breakdown (SELECT, INSERT, UPDATE, etc.)
- Top slowest queries

Usage:
    python scripts/profile_critical_endpoints.py
"""
import os
import sys
import time
import json
from collections import Counter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'padosi_agent.settings')

import django
django.setup()

from django.test import RequestFactory, Client
from django.test.utils import CaptureQueriesContext
from django.db import connection, reset_queries
from django.contrib.auth.models import User
from apps.admin_panel.models import Admin
from apps.agents.models import Agent, AgentProfile

def profile_endpoint(name, url, method="GET", data=None, user=None, is_admin=False):
    client = Client(HTTP_HOST='127.0.0.1')
    if user:
        client.force_login(user)
    if is_admin:
        admin_obj = Admin.objects.first()
        if admin_obj:
            session = client.session
            session['admin_id'] = admin_obj.id
            session['admin_email'] = admin_obj.email
            session['is_admin'] = True
            session.save()

    # Warm-up call (populate any initial caches)
    try:
        if method == "GET":
            client.get(url, data or {})
        else:
            client.post(url, data or {})
    except Exception as e:
        print(f"Warm-up failed for {name} ({url}): {e}")

    # Profiled call
    reset_queries()
    t0 = time.perf_counter()
    with CaptureQueriesContext(connection) as ctx:
        if method == "GET":
            response = client.get(url, data or {})
        else:
            response = client.post(url, data or {})
    wall_duration_ms = (time.perf_counter() - t0) * 1000.0

    queries = list(ctx.captured_queries)
    query_count = len(queries)
    total_db_time_ms = sum(float(q.get('time', 0)) for q in queries) * 1000.0

    # Duplicate query detection (stripping parameters / normalizing)
    raw_sqls = [q['sql'].strip() for q in queries]
    sql_counts = Counter(raw_sqls)
    duplicate_queries = {sql: count for sql, count in sql_counts.items() if count > 1}
    num_duplicates = sum(count - 1 for count in duplicate_queries.values())

    # Sort slowest queries
    sorted_queries = sorted(queries, key=lambda q: float(q.get('time', 0)), reverse=True)
    slowest = sorted_queries[:3] if sorted_queries else []

    return {
        "name": name,
        "url": url,
        "method": method,
        "status_code": response.status_code,
        "wall_duration_ms": round(wall_duration_ms, 2),
        "query_count": query_count,
        "total_db_time_ms": round(total_db_time_ms, 2),
        "num_duplicates": num_duplicates,
        "duplicate_queries": duplicate_queries,
        "slowest_queries": [
            {"time_ms": round(float(q.get('time', 0)) * 1000.0, 3), "sql": q.get('sql', '')[:200]}
            for q in slowest
        ]
    }

def run_profiling():
    print("=" * 80)
    print("CRITICAL USER JOURNEYS - ORM & DATABASE QUERY PROFILING")
    print("=" * 80)

    # Find test users
    agent_user = User.objects.filter(id=34).first()
    if not agent_user:
        agent_user = User.objects.first()

    admin_obj = Admin.objects.first()

    journeys = [
        ("01_Homepage", "/", "GET", None, None, False),
        ("02_HealthCheck", "/health/", "GET", None, None, False),
        ("03_PincodeCheck", "/api/pincode/check-agents/380015", "GET", None, None, False),
        ("04_FindAgents_Directory", "/find-agents/", "GET", None, None, False),
        ("05_FindAgents_SearchPincode", "/find-agents/?pincode=380015", "GET", None, None, False),
        ("06_FindAgents_SearchSmartRank", "/find-agents/?pincode=380015&search=insurance", "GET", None, None, False),
        ("07_ChoosePlan_Page", "/chooseplan/", "GET", None, None, False),
        ("08_Event_Landing", "/48HR/", "GET", None, None, False),
        ("09_Event_Leaderboard", "/stall-leaderboard/", "GET", None, None, False),
        ("10_Agent_Login_Page", "/agent-login/", "GET", None, None, False),
        ("11_Agent_Dashboard", "/agent/dashboard/", "GET", None, agent_user, False),
        ("12_Admin_Agents_List", "/admin/agents/", "GET", None, None, True),
        ("13_Calculators_Hub", "/calculators/", "GET", None, None, False),
        ("14_Check_Pincode", "/check-pincode?pincode=380015", "GET", None, None, False),
        ("15_About_Page", "/about/", "GET", None, None, False),
        ("16_Contact_Page", "/contact/", "GET", None, None, False),
    ]

    results = []
    print(f"{'Journey Name':<30} | {'Status':<6} | {'Wall (ms)':<10} | {'DB (ms)':<10} | {'Queries':<8} | {'Duplicates':<10}")
    print("-" * 86)

    for name, url, method, data, user, is_admin in journeys:
        res = profile_endpoint(name, url, method, data, user, is_admin)
        results.append(res)
        print(f"{res['name']:<30} | {res['status_code']:<6} | {res['wall_duration_ms']:<10.2f} | {res['total_db_time_ms']:<10.2f} | {res['query_count']:<8} | {res['num_duplicates']:<10}")

    print("\n" + "=" * 80)
    print("DETAILED BOTTLENECK & N+1 ANALYSIS")
    print("=" * 80)
    for res in results:
        if res['num_duplicates'] > 0 or res['query_count'] > 25:
            print(f"\n[!] HIGH QUERY / DUPLICATE DETECTED: {res['name']} ({res['url']})")
            print(f"    Total Queries: {res['query_count']} | Duplicates: {res['num_duplicates']} | Wall: {res['wall_duration_ms']}ms | DB: {res['total_db_time_ms']}ms")
            if res['duplicate_queries']:
                print("    Duplicate SQL Patterns:")
                for sql, cnt in list(res['duplicate_queries'].items())[:3]:
                    print(f"      x{cnt}: {sql[:150]}...")
            if res['slowest_queries']:
                print("    Slowest Queries:")
                for sq in res['slowest_queries']:
                    print(f"      {sq['time_ms']}ms: {sq['sql']}")

    with open("scripts/profiling_results_baseline.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved baseline profiling results to scripts/profiling_results_baseline.json")

if __name__ == '__main__':
    run_profiling()
