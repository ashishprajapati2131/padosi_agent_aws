# Self-healing: retries and circuit breakers

Shared helpers in `apps/admin_panel/services/resilience.py`.

## `retry_with_backoff(fn, ...)`

```python
from apps.admin_panel.services.resilience import retry_with_backoff

response = retry_with_backoff(
    lambda: requests.post(url, json=payload, timeout=20),
    attempts=3,
    base_delay=0.5,
    max_delay=8.0,
    retry_on=(requests.Timeout, requests.ConnectionError),
)
```

Backoff is exponential with **full jitter**: delay before attempt *n* is a
random value in `[0, min(max_delay, base_delay * 2 ** (n - 1))]`. Jitter is
important — without it every process that fails at the same time retries at the
same time, which is a thundering herd when a dependency recovers.

A `retry_on` outside the tuple raises immediately. Never catch `Exception` for
retry — it silently repeats programmer errors.

## `CircuitBreaker(name)`

State lives in the Django cache (shared across processes).

- **closed** — calls proceed. Each failure increments a counter.
- **open** — after `failure_threshold` (default 5) failures in a row, calls
  short-circuit with `CircuitBreakerOpen`. Blocks further calls for
  `cool_off_seconds` (default 60).
- **half_open** — one probe call is allowed. Success closes the breaker,
  failure reopens it for another cool-off.

Reset from the admin Recovery Centre (`reset_circuit_breaker` action) or by
clearing the cache key `cb:<name>`.

## `guarded_call(name, fn)`

One line to apply both:

```python
from apps.admin_panel.services.resilience import CircuitBreakerOpen, guarded_call

try:
    response = guarded_call("brevo", _attempt, retry_on=(requests.Timeout,))
except CircuitBreakerOpen:
    # Fall through to the next channel (SMTP here), queue, or skip.
    ...
```

## Where it's wired

| Service | File | Notes |
|---|---|---|
| Brevo email API | `apps/agents/services/brevo.py` | Fallback is already SMTP. When the breaker opens, email keeps going through SMTP. |

To add another: use `guarded_call` at the call site and append the breaker's
name to `known_breaker_names()` in `resilience.py` so the Recovery Centre's
Inspect/Reset actions can see it.

Still raw (not wrapped yet): FCM, Razorpay, Groq/Gemini/OpenRouter, Google
OAuth, Facebook Graph, IRDAI/AMFI scrapers, Cloudinary. Each is small to wrap
when its failures become a visible problem.

## What self-healing is NOT

- It does **not** restart services. The only restart hook in this project is
  `tmp/restart.txt` (Passenger), exposed through the Recovery Centre.
- It does **not** reconnect the database — Django does that, via
  `CONN_HEALTH_CHECKS=True` in settings.
- It does **not** retry forever. All limits are bounded; failures surface.
