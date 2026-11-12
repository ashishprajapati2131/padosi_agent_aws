"""retry_with_backoff + CircuitBreaker: small, isolated unit tests."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.admin_panel.services import resilience as r


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class RetryTests(SimpleTestCase):
    def test_returns_first_success(self):
        calls = []
        result = r.retry_with_backoff(
            lambda: calls.append(1) or "ok", sleep=lambda s: None
        )
        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 1)

    def test_retries_until_it_succeeds(self):
        count = {"n": 0}

        def flaky():
            count["n"] += 1
            if count["n"] < 3:
                raise ConnectionError("blip")
            return "ok"

        self.assertEqual(
            r.retry_with_backoff(flaky, attempts=5, sleep=lambda s: None),
            "ok",
        )
        self.assertEqual(count["n"], 3)

    def test_gives_up_after_attempts(self):
        count = {"n": 0}

        def always_fails():
            count["n"] += 1
            raise ConnectionError("down")

        with self.assertRaises(ConnectionError):
            r.retry_with_backoff(always_fails, attempts=4, sleep=lambda s: None)
        self.assertEqual(count["n"], 4)

    def test_non_retryable_exception_raises_immediately(self):
        count = {"n": 0}

        def wrong():
            count["n"] += 1
            raise ValueError("bug")

        with self.assertRaises(ValueError):
            r.retry_with_backoff(
                wrong, attempts=5, retry_on=(ConnectionError,), sleep=lambda s: None
            )
        self.assertEqual(count["n"], 1)

    def test_backoff_is_capped_with_jitter(self):
        delays = []

        def fail():
            raise ConnectionError("x")

        with self.assertRaises(ConnectionError):
            r.retry_with_backoff(
                fail,
                attempts=5,
                base_delay=1.0,
                max_delay=4.0,
                sleep=delays.append,
            )
        # 4 sleeps between 5 attempts, each within [0, cap] (cap grows 1→2→4→4)
        self.assertEqual(len(delays), 4)
        for d, cap in zip(delays, [1, 2, 4, 4]):
            self.assertGreaterEqual(d, 0.0)
            self.assertLessEqual(d, cap)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class CircuitBreakerTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_opens_after_threshold_and_blocks_further_calls(self):
        cb = r.CircuitBreaker(
            "svc", r.BreakerConfig(failure_threshold=3, cool_off_seconds=60)
        )
        for _ in range(2):
            self.assertTrue(cb.allow())
            cb.record_failure()
        self.assertEqual(cb.state()["state"], "closed")
        cb.record_failure()
        self.assertEqual(cb.state()["state"], "open")
        self.assertFalse(cb.allow())

    def test_cool_off_moves_to_half_open_then_closes_on_success(self):
        cb = r.CircuitBreaker(
            "svc", r.BreakerConfig(failure_threshold=1, cool_off_seconds=10)
        )
        cb.record_failure()
        self.assertFalse(cb.allow())
        with patch.object(r.time, "time", return_value=r.time.time() + 11):
            self.assertTrue(cb.allow())
            self.assertEqual(cb.state()["state"], "half_open")
            cb.record_success()
            self.assertEqual(cb.state()["state"], "closed")

    def test_half_open_failure_reopens_the_breaker(self):
        cb = r.CircuitBreaker(
            "svc", r.BreakerConfig(failure_threshold=1, cool_off_seconds=1)
        )
        cb.record_failure()
        with patch.object(r.time, "time", return_value=r.time.time() + 5):
            cb.allow()  # → half_open
            cb.record_failure()
            self.assertEqual(cb.state()["state"], "open")

    def test_reset_clears_state(self):
        cb = r.CircuitBreaker("svc", r.BreakerConfig(failure_threshold=1))
        cb.record_failure()
        cb.reset()
        self.assertEqual(cb.state()["state"], "closed")


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class GuardedCallTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_success_keeps_breaker_closed(self):
        r.guarded_call("svc", lambda: "ok")
        self.assertEqual(r.CircuitBreaker("svc").state()["state"], "closed")

    def test_failure_opens_breaker_and_next_call_short_circuits(self):
        config = r.BreakerConfig(failure_threshold=1, cool_off_seconds=60)

        with patch.object(r, "retry_with_backoff", side_effect=ConnectionError("down")):
            with self.assertRaises(ConnectionError):
                r.guarded_call("svc", lambda: None, config=config)

        self.assertEqual(r.CircuitBreaker("svc").state()["state"], "open")
        with self.assertRaises(r.CircuitBreakerOpen):
            r.guarded_call("svc", lambda: "never runs", config=config)
