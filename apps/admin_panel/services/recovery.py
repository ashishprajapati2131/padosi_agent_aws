"""Allowlisted recovery actions a Super Admin can run from the Server Health page.

Every action takes a Django request and returns a dict the view hands back as
JSON. No shell execution. Every action is audited by the caller.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.admin_panel.services.system_monitor import SystemMonitorService

logger = logging.getLogger(__name__)


# shortcut: queries are capped at 25 rows; raise it only once we need to see more.
_PROCESSLIST_LIMIT = 25


def _ok(**extra):
    out = {"ok": True}
    out.update(extra)
    return out


def _fail(message, **extra):
    out = {"ok": False, "message": message}
    out.update(extra)
    return out


def run_diagnostics(request) -> Dict[str, Any]:
    """Full metric snapshot and current threshold decision."""
    metrics = SystemMonitorService.get_metrics()
    is_critical, reasons, highest = SystemMonitorService.evaluate_threat(metrics)
    return _ok(
        metrics=metrics,
        reasons=reasons,
        highest_metric=highest,
        is_critical=is_critical,
        thresholds=SystemMonitorService.thresholds(),
    )


def test_database(request) -> Dict[str, Any]:
    """Bounded SELECT 1 round trip, with timing."""
    start = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
    except Exception as e:
        logger.warning("[recovery] test_database failed: %s", e)
        return _fail(f"{type(e).__name__}: {e}"[:200])
    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    return _ok(latency_ms=latency_ms, select_result=(row[0] if row else None))


def inspect_processlist(request) -> Dict[str, Any]:
    """Current MySQL processlist (non-sleep rows first, oldest at the top)."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW FULL PROCESSLIST")
            rows = cursor.fetchall()
    except Exception as e:
        return _fail(f"{type(e).__name__}: {e}"[:200])

    parsed = []
    for row in rows:
        if len(row) < 8:
            continue
        pid, user, host, db, cmd, t, state, info = row[:8]
        parsed.append(
            {
                "id": pid,
                "user": user,
                "host": host,
                "db": db,
                "command": cmd,
                "seconds": int(t or 0),
                "state": state,
                # Trim the SQL: the full text can be large and may carry PII.
                "info": (info[:200] if info else None),
            }
        )
    parsed.sort(key=lambda p: (str(p["command"]).lower() == "sleep", -p["seconds"]))
    return _ok(total=len(parsed), rows=parsed[:_PROCESSLIST_LIMIT])


def run_health_check(request) -> Dict[str, Any]:
    """Call the /health/ready endpoint in-process."""
    from django.test import RequestFactory

    from padosi_agent.views import health_check_view

    probe = RequestFactory().get("/health/ready")
    response = health_check_view(probe)
    try:
        body = response.content.decode("utf-8")
    except Exception:
        body = ""
    return _ok(status_code=response.status_code, body=body)


def verify_backup_status(request) -> Dict[str, Any]:
    """List what's in the backups/ folder, newest first."""
    backups_dir = Path(getattr(settings, "BASE_DIR", ".")) / "backups"
    if not backups_dir.exists():
        return _fail("backups/ folder is missing", path=str(backups_dir))
    files = []
    for entry in backups_dir.iterdir():
        if not entry.is_file():
            continue
        stat = entry.stat()
        files.append(
            {
                "name": entry.name,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "age_hours": round((time.time() - stat.st_mtime) / 3600, 1),
            }
        )
    files.sort(key=lambda f: f["age_hours"])
    newest = files[0] if files else None
    stale = newest is None or newest["age_hours"] > 36  # 24h cadence + 12h slack
    return _ok(
        path=str(backups_dir),
        files=files[:10],
        newest=newest,
        stale=stale,
    )


def resolve_incident(request) -> Dict[str, Any]:
    """Mark an open incident resolved (for a false positive you've checked)."""
    from apps.admin_panel.models import SystemIncident

    incident_id = (request.POST.get("incident_id") or "").strip()
    if not incident_id:
        return _fail("incident_id is required")
    try:
        incident = SystemIncident.objects.get(incident_id=incident_id)
    except SystemIncident.DoesNotExist:
        return _fail("Incident not found", incident_id=incident_id)
    if incident.resolved_at is not None:
        return _ok(incident_id=incident_id, already_resolved=True)
    incident.resolved_at = timezone.now()
    incident.save(update_fields=["resolved_at"])
    # Also clear the active-alert cache so the next failed check opens a new one.
    from django.core.cache import cache

    from apps.admin_panel.services.system_monitor import ACTIVE_ALERT_CACHE_KEY

    state = cache.get(ACTIVE_ALERT_CACHE_KEY)
    if isinstance(state, dict) and state.get("id") == incident_id:
        cache.delete(ACTIVE_ALERT_CACHE_KEY)
    return _ok(incident_id=incident_id)


def inspect_circuit_breakers(request) -> Dict[str, Any]:
    """Current state of every named circuit breaker."""
    from apps.admin_panel.services.resilience import CircuitBreaker, known_breaker_names

    rows = []
    for name in known_breaker_names():
        state = CircuitBreaker(name).state()
        rows.append({"name": name, **state})
    return _ok(breakers=rows)


def reset_circuit_breaker(request) -> Dict[str, Any]:
    """Force-close one breaker. Caller passes `breaker` in POST data."""
    from apps.admin_panel.services.resilience import CircuitBreaker, known_breaker_names

    name = (request.POST.get("breaker") or "").strip()
    if name not in known_breaker_names():
        return _fail("Unknown breaker", name=name, known=known_breaker_names())
    CircuitBreaker(name).reset()
    return _ok(reset=name)


def restart_workers(request) -> Dict[str, Any]:
    """Touch tmp/restart.txt — Passenger reloads the app on its next request.

    Destructive-ish: in-flight requests continue, but new ones wait for a fresh
    worker to boot. Caller must have passed confirmed=yes.
    """
    restart_file = Path(getattr(settings, "BASE_DIR", ".")) / "tmp" / "restart.txt"
    try:
        restart_file.parent.mkdir(parents=True, exist_ok=True)
        restart_file.touch()
        return _ok(touched=str(restart_file), mtime=os.path.getmtime(restart_file))
    except Exception as e:
        return _fail(f"{type(e).__name__}: {e}"[:200])


# name → (callable, "needs confirmation when truthy")
ACTIONS: Dict[str, Tuple[Callable[[Any], Dict[str, Any]], bool]] = {
    "run_diagnostics": (run_diagnostics, False),
    "test_database": (test_database, False),
    "inspect_processlist": (inspect_processlist, False),
    "run_health_check": (run_health_check, False),
    "verify_backup_status": (verify_backup_status, False),
    "inspect_circuit_breakers": (inspect_circuit_breakers, False),
    "reset_circuit_breaker": (reset_circuit_breaker, True),
    "resolve_incident": (resolve_incident, True),
    "restart_workers": (restart_workers, True),
}


def available_actions():
    """What the UI should render; order matters here."""
    return [
        {"name": name, "needs_confirmation": needs_confirmation}
        for name, (_, needs_confirmation) in ACTIONS.items()
    ]
