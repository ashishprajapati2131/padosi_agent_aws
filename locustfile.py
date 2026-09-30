"""
PadosiAgent High-Concurrency Load Testing Suite (Locust).

Simulates high-traffic event scenarios:
- Normal event landing page visitors (GET /event/)
- Pincode autocomplete lookups (GET /api/pincode/?pincode=380007)
- Live registration submissions (POST /agent-register-step1/)
- Duplicate / repeated submissions (idempotency verification)
- Public leaderboard polling (GET /event/leaderboard/)

Execution Scenarios:
====================
1. 5 RPS Warm-up:
   locust -f locustfile.py --headless --users 10 --spawn-rate 2 -t 1m --host https://padosiagent.com

2. 10 RPS Baseline:
   locust -f locustfile.py --headless --users 25 --spawn-rate 5 -t 2m --host https://padosiagent.com

3. 25 RPS Medium Concurrency:
   locust -f locustfile.py --headless --users 60 --spawn-rate 10 -t 3m --host https://padosiagent.com

4. 50 RPS Target Event Registration Load:
   locust -f locustfile.py --headless --users 120 --spawn-rate 20 -t 5m --host https://padosiagent.com

5. 100 RPS Burst Testing:
   locust -f locustfile.py --headless --users 250 --spawn-rate 50 -t 2m --host https://padosiagent.com
"""

import time
import uuid
import random
from locust import HttpUser, task, between, tag


class EventAttendeeUser(HttpUser):
    """
    Simulates a candidate registering during the event.
    Flow: Lands on /event/ -> checks pincode -> fills & posts Step 1 -> checks leaderboard.
    """
    wait_time = between(1.0, 3.0)

    def on_start(self):
        # Fetch event page to receive cookies and CSRF token
        response = self.client.get("/event/", name="01_GET_EventLanding")
        self.csrf_token = response.cookies.get('csrftoken', '')

    @task(4)
    @tag('registration')
    def register_step1(self):
        random_suffix = f"{random.randint(1000, 9999)}_{uuid.uuid4().hex[:4]}"
        random_mobile = f"98{random.randint(10000000, 99999999)}"
        test_email = f"loadtest_{random_suffix}@example.com"

        headers = {
            'X-CSRFToken': self.csrf_token,
            'Referer': f"{self.host}/event/",
        }

        # 1. Pincode lookup (cached or DB)
        self.client.get("/api/pincode/?pincode=380007", name="02_GET_PincodeLookup")

        # 2. Registration Step 1 submission
        payload = {
            'fullname': f'LoadTest Agent {random_suffix}',
            'email': test_email,
            'mobile': random_mobile,
            'agent_pincode': '380007',
            'state': 'Gujarat',
            'experience_range': '5',
            'segments[]': ['health', 'life'],
        }

        with self.client.post(
            "/agent-register-step1/",
            data=payload,
            headers=headers,
            catch_response=True,
            name="03_POST_RegisterStep1"
        ) as resp:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if data.get('success'):
                        resp.success()
                    else:
                        resp.failure(f"Registration failed logic: {data.get('message')}")
                except Exception as err:
                    resp.failure(f"Invalid JSON response: {err}")
            elif resp.status_code == 429:
                # Rate limit triggered: valid application defense mechanism
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:120]}")

    @task(2)
    @tag('leaderboard')
    def view_leaderboard(self):
        self.client.get("/event/leaderboard/", name="04_GET_Leaderboard")

    @task(1)
    @tag('duplicate_check')
    def simulate_duplicate_retry(self):
        """Simulate browser double-click or network retry with the same email."""
        headers = {
            'X-CSRFToken': self.csrf_token,
            'Referer': f"{self.host}/event/",
        }
        dup_email = "duplicate_benchmark@example.com"
        payload = {
            'fullname': 'Duplicate DoubleClick',
            'email': dup_email,
            'mobile': '9876543210',
            'agent_pincode': '380007',
            'state': 'Gujarat',
            'experience_range': '2',
            'segments[]': ['general'],
        }
        with self.client.post(
            "/agent-register-step1/",
            data=payload,
            headers=headers,
            catch_response=True,
            name="05_POST_DuplicateRetry"
        ) as resp:
            # 200 (idempotent update) or 422 (already registered active agent) or 429 (rate limited)
            if resp.status_code in (200, 422, 429):
                resp.success()
            else:
                resp.failure(f"Unexpected duplicate retry status: {resp.status_code}")


class SpectatorUser(HttpUser):
    """
    Simulates browsing traffic: viewing homepage, public profiles, and SEO pages.
    """
    wait_time = between(2.0, 5.0)

    @task(3)
    def visit_home(self):
        self.client.get("/", name="10_GET_Homepage")

    @task(2)
    def visit_leaderboard(self):
        self.client.get("/event/leaderboard/", name="11_GET_Leaderboard_Spectator")

    @task(1)
    def visit_health(self):
        self.client.get("/health/", name="12_GET_HealthCheck")
