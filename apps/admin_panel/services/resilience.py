"""Shared retry + circuit-breaker helpers for calls to external services.

- `retry_with_backoff(fn, ...)` — try a callable, backing off exponentially with
  jitter between attempts; raises the last exception if every attempt fails.
- `CircuitBreaker` — remembers failures of a named external service in the
  Django cache (shared across processes). After N consecutive failures the
  breaker opens and `allow()` returns False until a cool-off has passed; the
  first allowed call after that is a half-open probe and either closes the
  breaker on success or extends the cool-off on failure.

Both are designed to wrap external APIs (Brevo, Razorpay, FCM, LLM providers).
Use `guarded_call(name, fn)` to apply both at once.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Type

from django.core.cache import cache

logger = logging.getLogger(__name__)


def retry_with_backoff(
    fn: Callable[[], Any],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    retry_on: Iterable[Type[BaseException]] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Call `fn()` up to `attempts` times with exponential backoff + full jitter.

    Delay before attempt n (1-indexed) is random in [0, min(max_delay, base*2^(n-1))].
    Only exceptions in `retry_on` trigger a retry; others raise immediately so
    programmer errors never silently repeat.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    retry_on = tuple(retry_on)
    last: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except BaseException as exc:
            if not isinstance(exc, retry_on):
                raise
            last = exc
            if attempt >= attempts:
                break
            cap = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay = random.uniform(0, cap)
            logger.info(
                "[resilience] attempt %d/%d failed (%s); sleeping %.2fs",
                attempt,
                attempts,
                type(exc).__name__,
                delay,
            )
            sleep(delay)
    assert last is not None
    raise last


# ── Circuit breaker ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BreakerConfig:
    failure_threshold: int = 5
    cool_off_seconds: int = 60
    half_open_probe_window: int = 30  # a half-open probe has this long to settle


class CircuitBreakerOpen(RuntimeError):
    """Raised when a call is blocked because the breaker is open."""


class CircuitBreaker:
    """Lightweight, cache-backed breaker. Thread-safe only insofar as the cache is.

    State is one small dict per `name` in the Django cache:
        {"state": "closed"|"open"|"half_open", "failures": int, "opened_at": float}
    """

    STATES = ("closed", "open", "half_open")

    def __init__(self, name: str, config: BreakerConfig = None):
        self.name = name
        self.config = config or BreakerConfig()

    @property
    def _key(self) -> str:
        return f"cb:{self.name}"

    def state(self) -> dict:
        data = cache.get(self._key)
        if not isinstance(data, dict):
            return {"state": "closed", "failures": 0, "opened_at": 0.0}
        return data

    def _save(self, data: dict, timeout: int = 7 * 86400) -> None:
        try:
            cache.set(self._key, data, timeout=timeout)
        except Exception:
            logger.warning("[resilience] breaker %s: cache write failed", self.name)

    def allow(self) -> bool:
        """Return True if the next call may proceed. May move open → half_open."""
        data = self.state()
        if data["state"] == "closed":
            return True
        elapsed = time.time() - data["opened_at"]
        if data["state"] == "open" and elapsed >= self.config.cool_off_seconds:
            data["state"] = "half_open"
            data["opened_at"] = time.time()  # window for the probe
            self._save(data)
            return True
        if (
            data["state"] == "half_open"
            and elapsed >= self.config.half_open_probe_window
        ):
            # Lost probe (process died mid-call); let one more through.
            data["opened_at"] = time.time()
            self._save(data)
            return True
        return data["state"] != "open"

    def record_success(self) -> None:
        self._save({"state": "closed", "failures": 0, "opened_at": 0.0})

    def record_failure(self) -> None:
        data = self.state()
        data["failures"] = data.get("failures", 0) + 1
        if (
            data["state"] == "half_open"
            or data["failures"] >= self.config.failure_threshold
        ):
            data["state"] = "open"
            data["opened_at"] = time.time()
        self._save(data)

    def reset(self) -> None:
        cache.delete(self._key)


def guarded_call(
    name: str,
    fn: Callable[[], Any],
    *,
    config: BreakerConfig = None,
    retry: bool = True,
    attempts: int = 3,
    retry_on: Iterable[Type[BaseException]] = (Exception,),
) -> Any:
    """Run `fn` behind the named circuit breaker, with an optional retry.

    Raises `CircuitBreakerOpen` when the breaker is open. Caller decides what to
    do (queue, fall back, skip); this helper never silently swallows failures.
    """
    breaker = CircuitBreaker(name, config)
    if not breaker.allow():
        raise CircuitBreakerOpen(f"{name} breaker is open")
    try:
        if retry:
            result = retry_with_backoff(fn, attempts=attempts, retry_on=retry_on)
        else:
            result = fn()
    except Exception:
        breaker.record_failure()
        raise
    breaker.record_success()
    return result


def known_breaker_names() -> list:
    """Services this codebase treats as circuit-breaker protected, for UIs."""
    # Edit this list as you wire guarded_call() into more call sites.
    return ["brevo"]
