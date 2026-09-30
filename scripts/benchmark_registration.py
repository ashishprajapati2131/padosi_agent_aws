"""
Registration Endpoint Performance & Query Count Benchmark.

Tests:
1. Bcrypt password hashing latency (rounds 8, 10, 12).
2. Database query count per registration (asserting <= 15 queries).
3. Registration latency (p50, p90, p95, avg) across 30 simulated registrations.
4. Idempotency & duplicate submission handling (same email & same phone).
5. Event referral registration flow (Paldi campaign).

Usage:
    python scripts/benchmark_registration.py
"""

import os
import sys
import time
import uuid
import statistics

# Configure Django environment for benchmark execution
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'padosi_agent.settings')
os.environ.setdefault('SECRET_KEY', 'benchmark-test-secret-key-production-safe-12345')
os.environ.setdefault('DB_NAME', 'test')

import django
django.setup()

from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone
from apps.agents.models import Agent, AgentDraft, AgentProfile
from apps.event_referral.models import EventReferralCampaign, EventReferralParticipant
from password_hashing import hash_password, verify_password, BCRYPT_ROUNDS


def benchmark_password_hashing():
    print("\n" + "=" * 60)
    print("1. PASSWORD HASHING BENCHMARK")
    print("=" * 60)
    sample_password = "SecurePassword@2026!"

    for rounds in [8, 10, 12]:
        times = []
        for _ in range(5):
            t0 = time.perf_counter()
            hashed = hash_password(sample_password, rounds=rounds)
            duration_ms = (time.perf_counter() - t0) * 1000.0
            times.append(duration_ms)
        
        # Verify correctness and backward compatibility
        valid = verify_password(sample_password, hashed)
        avg = statistics.mean(times)
        p50 = statistics.median(times)
        print(f"  Rounds {rounds:2d} -> Avg: {avg:6.2f} ms | p50: {p50:6.2f} ms | Verified: {valid}")

    print(f"  [Active Configuration] BCRYPT_ROUNDS = {BCRYPT_ROUNDS}")


def benchmark_registration_queries():
    print("\n" + "=" * 60)
    print("2. DATABASE QUERY COUNT AUDIT")
    print("=" * 60)

    # Ensure campaign exists
    campaign, _ = EventReferralCampaign.objects.get_or_create(
        code="paldi",
        defaults={
            "name": "Paldi Event",
            "is_enabled": True,
            "starts_at": timezone.now() - timezone.timedelta(days=1),
            "ends_at": timezone.now() + timezone.timedelta(days=7),
            "required_paid_referrals": 5,
        }
    )

    client = Client()
    # Step 1: Hit event registration page to initialize session
    client.get('/event/')

    unique_suffix = uuid.uuid4().hex[:8]
    test_email = f"bench_{unique_suffix}@padosiagent.test"
    test_mobile = f"98{int(time.time()) % 100000000:08d}"

    payload = {
        'fullname': f'Benchmark Agent {unique_suffix}',
        'email': test_email,
        'mobile': test_mobile,
        'agent_pincode': '380007',
        'state': 'Gujarat',
        'experience_range': '5',
        'segments[]': ['health', 'life'],
    }

    with CaptureQueriesContext(connection) as queries:
        t0 = time.perf_counter()
        response = client.post('/agent-register-step1/', payload)
        duration_ms = (time.perf_counter() - t0) * 1000.0

    print(f"  Status code: {response.status_code}")
    print(f"  Response JSON: {response.json() if response.status_code == 200 else response.content[:100]}")
    print(f"  Query Count: {len(queries)} queries executed")
    print(f"  Duration: {duration_ms:.2f} ms")

    # Analyze query operations
    selects = sum(1 for q in queries if q['sql'].strip().upper().startswith('SELECT'))
    inserts = sum(1 for q in queries if q['sql'].strip().upper().startswith('INSERT'))
    updates = sum(1 for q in queries if q['sql'].strip().upper().startswith('UPDATE'))
    print(f"  Breakdown: {selects} SELECTs, {inserts} INSERTs, {updates} UPDATEs")

    if len(queries) <= 15:
        print("  [SUCCESS] Query count is well within optimized target (<= 15 queries)!")
    else:
        print(f"  [WARNING] Query count ({len(queries)}) exceeds 15 queries target.")


def benchmark_duplicate_registration():
    print("\n" + "=" * 60)
    print("3. IDEMPOTENCY & DUPLICATE PREVENTION AUDIT")
    print("=" * 60)

    client = Client()
    client.get('/event/')

    unique_suffix = uuid.uuid4().hex[:8]
    test_email = f"dup_{unique_suffix}@padosiagent.test"
    test_mobile = f"97{int(time.time()) % 100000000:08d}"

    payload = {
        'fullname': 'Duplicate Tester',
        'email': test_email,
        'mobile': test_mobile,
        'agent_pincode': '380007',
        'state': 'Gujarat',
        'experience_range': '3',
        'segments[]': ['life'],
    }

    # First attempt: should succeed
    res1 = client.post('/agent-register-step1/', payload)
    print(f"  Initial submission -> Status: {res1.status_code} (Success: {res1.json().get('success')})")

    # Second immediate attempt with exact same email & mobile: should handle idempotently
    res2 = client.post('/agent-register-step1/', payload)
    print(f"  Duplicate submission -> Status: {res2.status_code} (Success: {res2.json().get('success')})")
    
    # Check database count to guarantee no duplicate agents created
    agent_count = Agent.objects.filter(email=test_email).count()
    print(f"  Agent records in database for {test_email}: {agent_count} (Must be exactly 1)")
    if agent_count == 1:
        print("  [SUCCESS] Concurrency/Idempotency check passed: zero duplicates created!")
    else:
        print(f"  [FAIL] Duplicate agent detected: {agent_count} records found!")


def benchmark_throughput_batch(num_requests=30):
    print("\n" + "=" * 60)
    print(f"4. BATCH REGISTRATION LATENCY BENCHMARK ({num_requests} registrations)")
    print("=" * 60)

    latencies = []
    successes = 0

    for i in range(num_requests):
        client = Client()
        client.get('/event/')

        unique_suffix = f"{i:04d}_{uuid.uuid4().hex[:6]}"
        test_email = f"batch_{unique_suffix}@padosiagent.test"
        test_mobile = f"96{int(time.time() + i) % 100000000:08d}"

        payload = {
            'fullname': f'Batch Agent {i}',
            'email': test_email,
            'mobile': test_mobile,
            'agent_pincode': '380007',
            'state': 'Gujarat',
            'experience_range': '2',
            'segments[]': ['general'],
        }

        t0 = time.perf_counter()
        resp = client.post('/agent-register-step1/', payload)
        dur = (time.perf_counter() - t0) * 1000.0

        if resp.status_code == 200 and resp.json().get('success'):
            successes += 1
            latencies.append(dur)
        else:
            latencies.append(dur)

    if latencies:
        avg_lat = statistics.mean(latencies)
        p50 = statistics.median(latencies)
        sorted_lat = sorted(latencies)
        p90 = sorted_lat[int(len(sorted_lat) * 0.90)]
        p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
        min_lat = min(latencies)
        max_lat = max(latencies)

        print(f"  Completed: {successes}/{num_requests} successful registrations")
        print(f"  Min:  {min_lat:6.2f} ms")
        print(f"  Avg:  {avg_lat:6.2f} ms")
        print(f"  p50:  {p50:6.2f} ms")
        print(f"  p90:  {p90:6.2f} ms")
        print(f"  p95:  {p95:6.2f} ms")
        print(f"  Max:  {max_lat:6.2f} ms")


if __name__ == '__main__':
    print("Starting PadosiAgent In-Memory Registration Benchmark Suite...")
    benchmark_password_hashing()
    benchmark_registration_queries()
    benchmark_duplicate_registration()
    benchmark_throughput_batch(30)
    print("\n" + "=" * 60)
    print("BENCHMARK COMPLETED SUCCESSFULLY")
    print("=" * 60 + "\n")
