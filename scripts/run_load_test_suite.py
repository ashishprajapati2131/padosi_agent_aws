"""
Production-Style High-Concurrency Load Testing Suite.
Supports:
- Scenarios: Baseline (1, 5, 10), Normal (25, 50, 100), High (250), Stress, Spike, Soak.
- Realistic Traffic Mix across 20 critical endpoints.
- High-precision latency percentiles: Avg, P50, P90, P95, P99, Min, Max.
- System metrics: CPU %, Memory (MB and %), Error Rate %, Requests/Sec (RPS).
- Concurrency Safety Verification: Race conditions, duplicate registration attempts.

Usage:
    python scripts/run_load_test_suite.py --scenario all
    python scripts/run_load_test_suite.py --scenario baseline
    python scripts/run_load_test_suite.py --scenario normal
    python scripts/run_load_test_suite.py --scenario stress
    python scripts/run_load_test_suite.py --scenario spike
    python scripts/run_load_test_suite.py --scenario soak
    python scripts/run_load_test_suite.py --scenario concurrency
"""

import sys
import os
import time
import math
import json
import random
import asyncio
import psutil
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'padosi_agent.settings')
import django
django.setup()

import httpx

HOST = os.environ.get("LOADTEST_HOST", "http://127.0.0.1:8000")

# Realistic Production Traffic Mix
# 40% public/customer browsing
# 20% agent API / dashboard
# 10% search (pincode autocomplete, smart rank)
# 10% authentication / token refresh
# 10% lead / registration
# 5% admin
# 5% other (health, sitemap)
TRAFFIC_SPEC = [
    # Browsing (40%)
    {"weight": 20, "name": "Homepage", "method": "GET", "path": "/"},
    {"weight": 10, "name": "FindAgents_Directory", "method": "GET", "path": "/find-agents/"},
    {"weight": 5,  "name": "Calculators_Hub", "method": "GET", "path": "/calculators/"},
    {"weight": 5,  "name": "About_Page", "method": "GET", "path": "/about/"},

    # Agent API & Dashboard (20%)
    {"weight": 10, "name": "FastAPI_Plans", "method": "GET", "path": "/api/v1/agents/plans"},
    {"weight": 5,  "name": "FastAPI_Pincode", "method": "GET", "path": "/api/v1/pincode/380015"},
    {"weight": 5,  "name": "Django_PincodeCheck", "method": "GET", "path": "/api/pincode/check-agents/380015"},

    # Search & Smart Rank (10%)
    {"weight": 6,  "name": "FindAgents_PincodeSearch", "method": "GET", "path": "/find-agents/?pincode=380015"},
    {"weight": 4,  "name": "FindAgents_SmartRank", "method": "GET", "path": "/find-agents/?pincode=380015&search=insurance"},

    # Auth & Refresh (10%)
    {"weight": 5,  "name": "Agent_LoginPage", "method": "GET", "path": "/agent-login/"},
    {"weight": 5,  "name": "CSRF_Refresh", "method": "GET", "path": "/api/v1/csrf-refresh/"},

    # Lead & Registration (10%)
    {"weight": 6,  "name": "Register_Step1_Submit", "method": "POST", "path": "/agent-register-step1/", "is_reg": True},
    {"weight": 4,  "name": "Event_Landing", "method": "GET", "path": "/48HR/"},

    # Admin (5%)
    {"weight": 5,  "name": "Admin_LoginPage", "method": "GET", "path": "/admin/login/"},

    # Other / Monitoring (5%)
    {"weight": 3,  "name": "Django_Health", "method": "GET", "path": "/health/"},
    {"weight": 2,  "name": "FastAPI_Health", "method": "GET", "path": "/api/v1/health"},
]

POPULATION = []
for item in TRAFFIC_SPEC:
    POPULATION.extend([item] * item["weight"])

def percentile(data, p):
    if not data:
        return 0.0
    data_sorted = sorted(data)
    idx = (len(data_sorted) - 1) * p
    floor_idx = math.floor(idx)
    ceil_idx = math.ceil(idx)
    if floor_idx == ceil_idx:
        return data_sorted[int(idx)]
    d0 = data_sorted[floor_idx] * (ceil_idx - idx)
    d1 = data_sorted[ceil_idx] * (idx - floor_idx)
    return d0 + d1

async def worker(worker_id, stop_event, client, metrics_by_endpoint, global_latencies, global_status):
    while not stop_event.is_set():
        spec = random.choice(POPULATION)
        name = spec["name"]
        method = spec["method"]
        path = spec["path"]
        url = f"{HOST}{path}"

        headers = {}
        data = None

        if spec.get("is_reg"):
            rand_id = random.randint(100000, 999999)
            data = {
                "fullname": f"LoadTest User {rand_id}",
                "email": f"loadtest_{worker_id}_{rand_id}@example.test",
                "mobile": f"98{random.randint(10000000, 99999999)}",
                "agent_pincode": "380015",
                "state": "Gujarat",
                "experience_range": "3",
                "segments[]": ["health", "life"]
            }
            try:
                csrf_resp = await client.get(f"{HOST}/api/v1/csrf-refresh/", timeout=5.0)
                csrf_token = csrf_resp.json().get("csrf_token") or client.cookies.get("csrftoken", "")
            except Exception:
                csrf_token = client.cookies.get("csrftoken", "")
            headers["X-CSRFToken"] = csrf_token
            headers["Referer"] = f"{HOST}/agent-registration/"

        t0 = time.perf_counter()
        status = 0
        error_msg = None
        try:
            if method == "GET":
                resp = await client.get(url, headers=headers, timeout=15.0)
            elif method == "POST":
                resp = await client.post(url, data=data, headers=headers, timeout=15.0)
            status = resp.status_code
        except Exception as e:
            status = 0
            error_msg = str(e)
        duration_ms = (time.perf_counter() - t0) * 1000.0

        global_latencies.append(duration_ms)
        global_status[status] += 1

        ep_metric = metrics_by_endpoint[name]
        ep_metric["latencies"].append(duration_ms)
        ep_metric["status"][status] += 1
        if status not in (200, 201, 302, 422, 429):
            ep_metric["errors"] += 1

        # Small micro-pause between requests to mimic real user think time (5-20ms)
        await asyncio.sleep(random.uniform(0.005, 0.020))

async def run_scenario(name, concurrency, duration_sec):
    print(f"\n---> Running Scenario: {name} ({concurrency} concurrent users, {duration_sec}s sustained)")
    stop_event = asyncio.Event()
    metrics_by_endpoint = defaultdict(lambda: {"latencies": [], "status": defaultdict(int), "errors": 0})
    global_latencies = []
    global_status = defaultdict(int)

    limits = httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=concurrency)
    timeout = httpx.Timeout(15.0, connect=5.0)

    proc = psutil.Process()
    cpu_before = psutil.cpu_percent(interval=None)
    mem_before = proc.memory_info().rss / (1024 * 1024)

    t_start = time.perf_counter()
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        tasks = [
            asyncio.create_task(worker(i, stop_event, client, metrics_by_endpoint, global_latencies, global_status))
            for i in range(concurrency)
        ]

        await asyncio.sleep(duration_sec)
        stop_event.set()
        await asyncio.gather(*tasks, return_exceptions=True)

    total_time = time.perf_counter() - t_start
    cpu_after = psutil.cpu_percent(interval=None)
    mem_after = proc.memory_info().rss / (1024 * 1024)

    total_reqs = len(global_latencies)
    rps = total_reqs / total_time if total_time > 0 else 0
    errors = sum(count for st, count in global_status.items() if st not in (200, 201, 302, 422, 429))
    error_rate = (errors / total_reqs * 100.0) if total_reqs > 0 else 0.0

    avg_lat = (sum(global_latencies) / total_reqs) if total_reqs else 0
    p50_lat = percentile(global_latencies, 0.50)
    p90_lat = percentile(global_latencies, 0.90)
    p95_lat = percentile(global_latencies, 0.95)
    p99_lat = percentile(global_latencies, 0.99)
    min_lat = min(global_latencies) if global_latencies else 0
    max_lat = max(global_latencies) if global_latencies else 0

    print(f"     Results for {name}:")
    print(f"       Requests: {total_reqs} | Duration: {total_time:.2f}s | RPS: {rps:.1f}")
    print(f"       Avg: {avg_lat:.2f}ms | P50: {p50_lat:.2f}ms | P95: {p95_lat:.2f}ms | P99: {p99_lat:.2f}ms | Max: {max_lat:.2f}ms")
    print(f"       Error Rate: {error_rate:.2f}% ({errors}/{total_reqs})")
    print(f"       CPU: {cpu_after:.1f}% | Memory: {mem_after:.1f} MB (Delta: +{mem_after - mem_before:.2f} MB)")
    print(f"       Status Codes: {dict(global_status)}")

    # Endpoint breakdown
    summary_endpoints = {}
    for ep_name, data in metrics_by_endpoint.items():
        lats = data["latencies"]
        cnt = len(lats)
        summary_endpoints[ep_name] = {
            "count": cnt,
            "avg_ms": round(sum(lats) / cnt, 2) if cnt else 0,
            "p50_ms": round(percentile(lats, 0.50), 2),
            "p95_ms": round(percentile(lats, 0.95), 2),
            "p99_ms": round(percentile(lats, 0.99), 2),
            "errors": data["errors"],
            "rps": round(cnt / total_time, 2) if total_time > 0 else 0
        }

    return {
        "name": name,
        "concurrency": concurrency,
        "duration_sec": total_time,
        "total_requests": total_reqs,
        "rps": round(rps, 2),
        "avg_ms": round(avg_lat, 2),
        "p50_ms": round(p50_lat, 2),
        "p90_ms": round(p90_lat, 2),
        "p95_ms": round(p95_lat, 2),
        "p99_ms": round(p99_lat, 2),
        "min_ms": round(min_lat, 2),
        "max_ms": round(max_lat, 2),
        "errors": errors,
        "error_rate_pct": round(error_rate, 2),
        "cpu_pct": cpu_after,
        "memory_mb": round(mem_after, 2),
        "status_distribution": dict(global_status),
        "endpoints": summary_endpoints
    }

async def run_concurrency_race_test():
    print("\n" + "=" * 80)
    print("CONCURRENCY INTEGRITY & RACE CONDITION TEST")
    print("=" * 80)
    print("Simulating simultaneous submissions with identical credentials & identical pincodes...")

    url = f"{HOST}/agent-register-step1/"
    test_email = f"race_condition_{random.randint(1000, 9999)}@test.com"
    test_mobile = f"97{random.randint(10000000, 99999999)}"

    payload = {
        "fullname": "Race Condition Agent",
        "email": test_email,
        "mobile": test_mobile,
        "agent_pincode": "380015",
        "state": "Gujarat",
        "experience_range": "5",
        "segments[]": ["health", "life"]
    }

    # Fire 10 identical requests simultaneously
    async with httpx.AsyncClient(timeout=10.0) as client:
        csrf_resp = await client.get(f"{HOST}/api/v1/csrf-refresh/")
        csrf_token = csrf_resp.json().get("csrf_token") or client.cookies.get("csrftoken", "")
        headers = {
            "X-CSRFToken": csrf_token,
            "Referer": f"{HOST}/agent-registration/",
        }
        reqs = [client.post(url, data=payload, headers=headers) for _ in range(10)]
        results = await asyncio.gather(*reqs, return_exceptions=True)

    statuses = [r.status_code if isinstance(r, httpx.Response) else str(r) for r in results]
    print(f"Results of 10 simultaneous registration submissions for '{test_email}':")
    print(f"  Statuses: {Counter(statuses)}")

    # Verify no duplicate AgentDraft records were created in the database
    from asgiref.sync import sync_to_async
    from apps.agents.models import AgentDraft
    from django.db import connection

    def check_drafts():
        connection.close()
        return AgentDraft.objects.filter(email=test_email).count()

    draft_count = await sync_to_async(check_drafts)()
    print(f"  Database Verification: AgentDraft records created = {draft_count} (Expected: 1)")
    assert draft_count == 1, f"RACE CONDITION DETECTED: {draft_count} drafts created!"
    print("  [PASS] Concurrency integrity verified: No duplicate records or race conditions.")

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="PadosiAgent Production Load Testing Suite")
    parser.add_argument("--scenario", choices=["baseline", "normal", "high", "stress", "spike", "soak", "concurrency", "all"], default="all")
    parser.add_argument("--output", default="scripts/load_test_results_baseline.json", help="Path to save output JSON")
    args = parser.parse_args()

    all_results = {}
    output_path = args.output

    def save_checkpoint():
        with open(output_path, "w") as f:
            json.dump(all_results, f, indent=2)

    if args.scenario in ("baseline", "all"):
        print("\n" + "=" * 80)
        print("SCENARIO A: BASELINE LOAD (Normal response time measurement)")
        print("=" * 80)
        all_results["baseline_1"] = await run_scenario("Baseline_1_User", 1, 10)
        save_checkpoint()
        all_results["baseline_5"] = await run_scenario("Baseline_5_Users", 5, 10)
        save_checkpoint()
        all_results["baseline_10"] = await run_scenario("Baseline_10_Users", 10, 10)
        save_checkpoint()

    if args.scenario in ("normal", "all"):
        print("\n" + "=" * 80)
        print("SCENARIO B: NORMAL LOAD")
        print("=" * 80)
        all_results["normal_25"] = await run_scenario("Normal_25_Users", 25, 15)
        save_checkpoint()
        all_results["normal_50"] = await run_scenario("Normal_50_Users", 50, 15)
        save_checkpoint()
        all_results["normal_100"] = await run_scenario("Normal_100_Users", 100, 15)
        save_checkpoint()

    if args.scenario in ("high", "all"):
        print("\n" + "=" * 80)
        print("SCENARIO C: HIGH LOAD")
        print("=" * 80)
        all_results["high_250"] = await run_scenario("High_250_Users", 250, 20)
        save_checkpoint()

    if args.scenario in ("stress", "all"):
        print("\n" + "=" * 80)
        print("SCENARIO D: STRESS TEST (Finding Saturation Threshold)")
        print("=" * 80)
        for users in [350, 500]:
            res = await run_scenario(f"Stress_{users}_Users", users, 15)
            all_results[f"stress_{users}"] = res
            save_checkpoint()
            if res["error_rate_pct"] > 5.0 or res["p95_ms"] > 3000:
                print(f"     [!] Saturation threshold reached at {users} users.")
                break

    if args.scenario in ("spike", "all"):
        print("\n" + "=" * 80)
        print("SCENARIO E: SPIKE TEST (Sudden 10 -> 100 -> 250 burst and recovery)")
        print("=" * 80)
        all_results["spike_pre"] = await run_scenario("Spike_Pre_10", 10, 5)
        save_checkpoint()
        all_results["spike_burst_100"] = await run_scenario("Spike_Burst_100", 100, 5)
        save_checkpoint()
        all_results["spike_burst_250"] = await run_scenario("Spike_Burst_250", 250, 5)
        save_checkpoint()
        all_results["spike_recovery"] = await run_scenario("Spike_Recovery_10", 10, 5)
        save_checkpoint()

    if args.scenario in ("soak", "all"):
        print("\n" + "=" * 80)
        print("SCENARIO F: SOAK / ENDURANCE TEST (Sustained traffic for leak detection)")
        print("=" * 80)
        all_results["soak_50"] = await run_scenario("Soak_50_Users", 50, 30)
        save_checkpoint()

    if args.scenario in ("concurrency", "all"):
        await run_concurrency_race_test()

    save_checkpoint()
    print(f"\n[OK] All load test metrics written to {output_path}")

if __name__ == "__main__":
    from collections import Counter
    asyncio.run(main())
