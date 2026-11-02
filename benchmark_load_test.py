#!/usr/bin/env python3
"""
PadosiAgent Real-World User Concurrency & Load Benchmark Script
Simulates realistic concurrent user journeys against the application,
recording exact response times, percentiles (p50, p90, p95, p99),
Requests Per Second (RPS), throughput, error rates, and saturation limits.
"""

import sys
import time
import math
import asyncio
import aiohttp
import random
import argparse
from typing import List, Dict, Any
from dataclasses import dataclass, field

# Reconfigure stdout/stderr to UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# User agent to avoid bot-shield 403 blocks
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,gu;q=0.8",
}

# Real user journeys across key system pages & APIs
USER_FLOWS = [
    {
        "name": "General Visitor (Browsing)",
        "weight": 35,
        "steps": [
            ("/", "GET"),
            ("/about/", "GET"),
            ("/faq/", "GET"),
            ("/calculators/", "GET"),
        ],
    },
    {
        "name": "Lead / Agent Searcher (Database Intensive)",
        "weight": 35,
        "steps": [
            ("/", "GET"),
            ("/find-agents/", "GET"),
            ("/api/pincode/check-agents/380007", "GET"),
            ("/insurance/api/pincode/fetch/380007", "GET"),
        ],
    },
    {
        "name": "Event & Leaderboard Participant",
        "weight": 20,
        "steps": [
            ("/48HR/", "GET"),
            ("/stall-leaderboard/", "GET"),
            ("/health/", "GET"),
        ],
    },
    {
        "name": "Lightweight API / Status Monitor",
        "weight": 10,
        "steps": [
            ("/health/", "GET"),
        ],
    },
]


@dataclass
class RequestResult:
    url: str
    status: int
    duration_ms: float
    bytes_transferred: int
    error: str = ""


@dataclass
class StageMetrics:
    concurrent_users: int
    duration_sec: float
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limited_429: int = 0
    server_errors_5xx: int = 0
    other_errors: int = 0
    rps: float = 0.0
    throughput_kb_s: float = 0.0
    min_ms: float = 0.0
    avg_ms: float = 0.0
    p50_ms: float = 0.0
    p90_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    max_ms: float = 0.0
    latencies: List[float] = field(default_factory=list)
    endpoint_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)


def calculate_percentile(sorted_list: List[float], p: float) -> float:
    if not sorted_list:
        return 0.0
    k = (len(sorted_list) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_list[int(k)]
    d0 = sorted_list[int(f)] * (c - k)
    d1 = sorted_list[int(c)] * (k - f)
    return d0 + d1


async def simulate_user(
    session: aiohttp.ClientSession,
    base_url: str,
    stop_event: asyncio.Event,
    results: List[RequestResult],
    think_time_min: float = 0.5,
    think_time_max: float = 1.5,
):
    """Simulates a single active user executing typical journeys."""
    flows = [f for f in USER_FLOWS for _ in range(f["weight"])]

    while not stop_event.is_set():
        flow = random.choice(flows)
        for endpoint, method in flow["steps"]:
            if stop_event.is_set():
                break

            url = f"{base_url.rstrip('/')}{endpoint}"
            start_time = time.perf_counter()
            status = 0
            bytes_len = 0
            err_msg = ""

            try:
                if method == "GET":
                    async with session.get(url, headers=HEADERS, allow_redirects=True) as resp:
                        body = await resp.read()
                        status = resp.status
                        bytes_len = len(body)
                elif method == "POST":
                    async with session.post(url, headers=HEADERS, allow_redirects=True) as resp:
                        body = await resp.read()
                        status = resp.status
                        bytes_len = len(body)
            except asyncio.TimeoutError:
                status = 408
                err_msg = "Timeout"
            except aiohttp.ClientConnectorError as e:
                status = 599
                err_msg = f"Connection error: {e}"
            except Exception as e:
                status = 599
                err_msg = str(e)

            duration_ms = (time.perf_counter() - start_time) * 1000.0
            results.append(
                RequestResult(
                    url=endpoint,
                    status=status,
                    duration_ms=duration_ms,
                    bytes_transferred=bytes_len,
                    error=err_msg,
                )
            )

            # Realistic human think time between clicks
            await asyncio.sleep(random.uniform(think_time_min, think_time_max))


async def run_stage(
    base_url: str,
    concurrent_users: int,
    duration_sec: int,
    think_time_min: float,
    think_time_max: float,
) -> StageMetrics:
    print(f"\n=======================================================")
    print(f">> Running Stage: {concurrent_users} Concurrent Users for {duration_sec}s")
    print(f"=======================================================")

    results: List[RequestResult] = []
    stop_event = asyncio.Event()

    # Limit TCP connections to avoid client-side exhaustion
    conn = aiohttp.TCPConnector(limit=concurrent_users + 50, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=20, connect=10)

    start_stage = time.perf_counter()

    async with aiohttp.ClientSession(connector=conn, timeout=timeout) as session:
        workers = [
            asyncio.create_task(
                simulate_user(
                    session,
                    base_url,
                    stop_event,
                    results,
                    think_time_min,
                    think_time_max,
                )
            )
            for _ in range(concurrent_users)
        ]

        # Wait duration
        await asyncio.sleep(duration_sec)
        stop_event.set()

        # Let current pending requests settle
        await asyncio.gather(*workers, return_exceptions=True)

    total_stage_time = time.perf_counter() - start_stage

    # Compute metrics
    metrics = StageMetrics(
        concurrent_users=concurrent_users,
        duration_sec=total_stage_time,
    )
    metrics.total_requests = len(results)

    if not results:
        print("[WARN] No requests completed in this stage.")
        return metrics

    latencies = []
    total_bytes = 0
    endpoint_groups: Dict[str, List[RequestResult]] = {}

    for r in results:
        latencies.append(r.duration_ms)
        total_bytes += r.bytes_transferred

        if 200 <= r.status < 400:
            metrics.successful_requests += 1
        elif r.status == 429:
            metrics.rate_limited_429 += 1
            metrics.failed_requests += 1
        elif 500 <= r.status < 600:
            metrics.server_errors_5xx += 1
            metrics.failed_requests += 1
        else:
            metrics.other_errors += 1
            metrics.failed_requests += 1

        if r.url not in endpoint_groups:
            endpoint_groups[r.url] = []
        endpoint_groups[r.url].append(r)

    latencies.sort()
    metrics.latencies = latencies
    metrics.rps = metrics.total_requests / total_stage_time
    metrics.throughput_kb_s = (total_bytes / 1024.0) / total_stage_time
    metrics.min_ms = latencies[0]
    metrics.avg_ms = sum(latencies) / len(latencies)
    metrics.p50_ms = calculate_percentile(latencies, 50)
    metrics.p90_ms = calculate_percentile(latencies, 90)
    metrics.p95_ms = calculate_percentile(latencies, 95)
    metrics.p99_ms = calculate_percentile(latencies, 99)
    metrics.max_ms = latencies[-1]

    # Per-endpoint breakdown
    for ep, ep_results in endpoint_groups.items():
        ep_lats = sorted([x.duration_ms for x in ep_results])
        ep_success = sum(1 for x in ep_results if 200 <= x.status < 400)
        metrics.endpoint_stats[ep] = {
            "calls": len(ep_results),
            "success": ep_success,
            "fail": len(ep_results) - ep_success,
            "avg_ms": sum(ep_lats) / len(ep_lats),
            "p95_ms": calculate_percentile(ep_lats, 95),
        }

    # Print Stage Summary
    success_pct = (metrics.successful_requests / metrics.total_requests) * 100
    print(f"  * Total Requests Completed: {metrics.total_requests}")
    print(f"  * Success Rate:             {success_pct:.1f}% ({metrics.successful_requests}/{metrics.total_requests})")
    if metrics.failed_requests > 0:
        print(f"  * Failed Requests:          {metrics.failed_requests} (429 RateLimit: {metrics.rate_limited_429}, 5xx ServerErrors: {metrics.server_errors_5xx}, Other: {metrics.other_errors})")
    print(f"  * Requests/sec (RPS):       {metrics.rps:.2f} req/s")
    print(f"  * Bandwidth Throughput:     {metrics.throughput_kb_s:.2f} KB/s")
    print(f"  * Latency (Median p50):     {metrics.p50_ms:.1f} ms")
    print(f"  * Latency (p90):            {metrics.p90_ms:.1f} ms")
    print(f"  * Latency (p95):            {metrics.p95_ms:.1f} ms")
    print(f"  * Latency (p99):            {metrics.p99_ms:.1f} ms")
    print(f"  * Latency (Min / Max):      {metrics.min_ms:.1f} ms / {metrics.max_ms:.1f} ms")

    return metrics


async def main():
    parser = argparse.ArgumentParser(description="PadosiAgent User Concurrency Load Benchmark")
    parser.add_argument("--host", default="https://padosiagent.com", help="Target Base URL")
    parser.add_argument("--users", type=int, default=None, help="Specific number of concurrent users to test")
    parser.add_argument("--duration", type=int, default=15, help="Duration in seconds per test stage")
    parser.add_argument("--fast", action="store_true", help="Quick run across stages (10s per stage)")
    args = parser.parse_args()

    base_url = args.host
    duration = 10 if args.fast else args.duration

    print("=================================================================")
    print("      PADOSI AGENT CONCURRENT USER LOAD TESTING BENCHMARK         ")
    print(f"  Target Server: {base_url}")
    print(f"  Duration per Tier: {duration}s")
    print("=================================================================")

    # Verify server connectivity first
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as s:
            async with s.get(f"{base_url.rstrip('/')}/health/", timeout=aiohttp.ClientTimeout(total=8)) as r:
                print(f"[OK] Initial Connectivity Check: Health Endpoint returned HTTP {r.status}")
    except Exception as e:
        print(f"[ERROR] Server unreachable at {base_url}: {e}")
        sys.exit(1)

    if args.users:
        tiers = [args.users]
    else:
        # Standard escalation curve: 10 -> 25 -> 50 -> 100 -> 150 -> 200 -> 300
        tiers = [10, 25, 50, 100, 150, 200]

    all_stage_metrics: List[StageMetrics] = []

    for user_count in tiers:
        stage_result = await run_stage(
            base_url=base_url,
            concurrent_users=user_count,
            duration_sec=duration,
            think_time_min=0.3,
            think_time_max=1.0,
        )
        all_stage_metrics.append(stage_result)

        # Early termination condition if server completely collapses (>40% errors)
        if stage_result.total_requests > 0:
            failure_rate = stage_result.failed_requests / stage_result.total_requests
            if failure_rate > 0.40:
                print(f"\n[ALERT] Critical Threshold Exceeded! Failure rate hit {failure_rate*100:.1f}%. Halting further escalation to prevent sustained downtime.")
                break

        # Cool-down between stages
        print("[INFO] Cooling down for 3 seconds...")
        await asyncio.sleep(3)

    # FINAL REPORT CONSOLIDATION
    print("\n" + "=" * 80)
    print("                      FINAL LOAD TEST RESULTS                     ")
    print("=" * 80)
    print(f"{'Users':<8}{'RPS':<10}{'Total Req':<12}{'Success %':<12}{'p50 (ms)':<12}{'p95 (ms)':<12}{'Max (ms)':<10}")
    print("-" * 80)
    for m in all_stage_metrics:
        succ_pct = (m.successful_requests / m.total_requests * 100) if m.total_requests > 0 else 0
        print(f"{m.concurrent_users:<8}{m.rps:<10.2f}{m.total_requests:<12}{succ_pct:<12.1f}{m.p50_ms:<12.1f}{m.p95_ms:<12.1f}{m.max_ms:<10.1f}")
    print("=" * 80)

    # Output detailed JSON summary
    import json
    report_data = {
        "target": base_url,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stages": [
            {
                "concurrent_users": m.concurrent_users,
                "duration_sec": m.duration_sec,
                "total_requests": m.total_requests,
                "success_rate_pct": (m.successful_requests / m.total_requests * 100) if m.total_requests > 0 else 0,
                "rps": round(m.rps, 2),
                "throughput_kb_s": round(m.throughput_kb_s, 2),
                "latency_p50_ms": round(m.p50_ms, 1),
                "latency_p90_ms": round(m.p90_ms, 1),
                "latency_p95_ms": round(m.p95_ms, 1),
                "latency_p99_ms": round(m.p99_ms, 1),
                "latency_max_ms": round(m.max_ms, 1),
                "errors": {
                    "429_rate_limit": m.rate_limited_429,
                    "5xx_server_error": m.server_errors_5xx,
                    "other": m.other_errors,
                },
                "endpoints": m.endpoint_stats,
            }
            for m in all_stage_metrics
        ],
    }

    report_path = "load_test_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    print(f"\n[REPORT] Detailed machine-readable report written to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
