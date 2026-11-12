"""
Automated High-Load & Crash Prevention Alerting System — PadosiAgent
====================================================================
Monitors CPU, Memory (RAM), Disk Space, and MySQL Connection Saturation.
When system load exceeds 95% (or custom threshold), proactively triggers
an urgent email alert with live diagnostic metrics and step-by-step
emergency remediation instructions before the website goes down.

Recipients:
- Primary: Admin email (padosiagent@gmail.com / settings.ADMIN_ALERT_EMAIL)
- CC: parth.ramanujj@gmail.com

Includes intelligent cooldown throttling (15 minutes) to avoid mail flooding.
"""

import time
import socket
import logging
from datetime import datetime, timezone as dt_timezone
from typing import Dict, Any, List, Tuple

import psutil
from django.conf import settings
from django.db import connection
from django.core.cache import cache
from django.utils.html import escape

from apps.agents.services.brevo import email_service

logger = logging.getLogger(__name__)

# Default critical threshold (kept for callers that still pass a single value)
DEFAULT_CRITICAL_THRESHOLD = 95.0

# Per-metric warning and critical thresholds (percent). Override any of them in
# Django settings as SYSTEM_MONITOR_THRESHOLDS = {"cpu": {"warning": 80, "critical": 95}, ...}.
DEFAULT_THRESHOLDS = {
    "cpu": {"warning": 75.0, "critical": 95.0},
    "ram": {"warning": 80.0, "critical": 95.0},
    "disk": {"warning": 80.0, "critical": 95.0},
    "db": {"warning": 75.0, "critical": 90.0},
}

# Number of back-to-back failing checks required before emailing. One blip of
# high CPU or a single dropped query should not wake anyone up.
# Override with settings.SYSTEM_MONITOR_CONSECUTIVE_FAILURES.
DEFAULT_CONSECUTIVE_FAILURES = 2

# Alert cooldown in seconds (15 minutes) to prevent email storms while load is high
ALERT_COOLDOWN_SECONDS = 900
COOLDOWN_CACHE_KEY = "system_load_alert_cooldown_timestamp"
# Set while an alert is open, so the first healthy check sends one recovery email.
ACTIVE_ALERT_CACHE_KEY = "system_load_alert_active"

DB_OK = "healthy"
DB_UNREACHABLE = "UNREACHABLE"
# shortcut: failure is verified by an in-check retry only, not across runs;
# move to consecutive-run counting if single-minute blips still alert.
DB_CHECK_ATTEMPTS = 2
DB_RETRY_DELAY_SECONDS = 3

# Designated alert recipients
DEFAULT_ADMIN_EMAIL = getattr(settings, "ADMIN_ALERT_EMAIL", "padosiagent@gmail.com")
MANDATORY_CC_EMAIL = "parth.ramanujj@gmail.com"


class SystemMonitorService:
    """
    Central service for server health inspection, load metric collection,
    and proactive emergency alerting.
    """

    @classmethod
    def get_metrics(cls) -> Dict[str, Any]:
        """
        Collect real-time CPU, RAM, Disk, MySQL, and Process metrics.
        """
        metrics = {
            # USE_TZ=False: local time is IST, so UTC is taken explicitly (the old label said UTC on an IST value).
            "timestamp": (
                f"{datetime.now(dt_timezone.utc):%Y-%m-%d %H:%M:%S} UTC"
                f" / {datetime.now():%H:%M:%S} {settings.TIME_ZONE}"
            ),
            "hostname": socket.gethostname(),
            "cpu_percent": 0.0,
            "ram_percent": 0.0,
            "ram_used_mb": 0,
            "ram_total_mb": 0,
            "ram_available_mb": 0,
            "disk_percent": 0.0,
            "disk_used_gb": 0.0,
            "disk_total_gb": 0.0,
            "disk_free_gb": 0.0,
            # None = not measured. A failed collection must never read as 0 or 100.
            "db_status": DB_OK,
            "db_error": None,
            "db_threads_connected": None,
            "db_max_connections": None,
            "db_connection_percent": None,
            "db_display": "UNAVAILABLE",
            "db_slow_queries": 0,
            "db_locked_queries_count": 0,
            "top_processes": [],
            "error": None,
        }

        # 1. CPU Metrics (sampled over 0.3s)
        try:
            metrics["cpu_percent"] = round(psutil.cpu_percent(interval=0.3), 1)
        except Exception as e:
            logger.warning(f"[SystemMonitor] CPU check failed: {e}")

        # 2. RAM / Memory Metrics
        try:
            vm = psutil.virtual_memory()
            metrics["ram_percent"] = round(vm.percent, 1)
            metrics["ram_used_mb"] = int(vm.used // (1024 * 1024))
            metrics["ram_total_mb"] = int(vm.total // (1024 * 1024))
            metrics["ram_available_mb"] = int(vm.available // (1024 * 1024))
        except Exception as e:
            logger.warning(f"[SystemMonitor] RAM check failed: {e}")

        # 3. Disk Metrics (root partition)
        try:
            disk = psutil.disk_usage("/")
            metrics["disk_percent"] = round(disk.percent, 1)
            metrics["disk_used_gb"] = round(disk.used / (1024**3), 1)
            metrics["disk_total_gb"] = round(disk.total / (1024**3), 1)
            metrics["disk_free_gb"] = round(disk.free / (1024**3), 1)
        except Exception as e:
            logger.warning(f"[SystemMonitor] Disk check failed: {e}")

        # 4. Database (MySQL) Metrics. One dropped connection (e.g. MySQL 2013) is
        # not an outage: retry on a fresh connection before calling it unreachable.
        for attempt in range(1, DB_CHECK_ATTEMPTS + 1):
            try:
                cls._collect_db_metrics(metrics)
                metrics["db_status"], metrics["db_error"] = DB_OK, None
                break
            except Exception as e:
                metrics["db_status"] = DB_UNREACHABLE
                metrics["db_error"] = f"{type(e).__name__}: {e}"[:300]
                logger.error(
                    f"[SystemMonitor] MySQL check failed (attempt {attempt}/{DB_CHECK_ATTEMPTS}): {e}"
                )
                try:
                    connection.close()  # drop the broken connection; the next attempt reconnects
                except Exception:
                    pass
                if attempt < DB_CHECK_ATTEMPTS:
                    time.sleep(DB_RETRY_DELAY_SECONDS)

        if (
            metrics["db_status"] == DB_OK
            and metrics["db_connection_percent"] is not None
        ):
            metrics["db_display"] = (
                f"{metrics['db_connection_percent']}% "
                f"({metrics['db_threads_connected']}/{metrics['db_max_connections']})"
            )
        else:
            # Unreachable, or reachable but the counters could not be read.
            metrics["db_threads_connected"] = metrics["db_max_connections"] = None
            metrics["db_connection_percent"] = None

        # 5. Top 5 CPU/Memory consuming processes
        try:
            procs_list = []
            for p in psutil.process_iter(
                ["pid", "name", "cpu_percent", "memory_percent"]
            ):
                try:
                    info = p.info
                    procs_list.append(
                        {
                            "pid": info["pid"],
                            "name": info["name"],
                            "cpu": round(info["cpu_percent"] or 0.0, 1),
                            "mem": round(info["memory_percent"] or 0.0, 1),
                        }
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Sort by CPU desc
            top_procs = sorted(
                procs_list, key=lambda x: (x["cpu"], x["mem"]), reverse=True
            )[:5]
            metrics["top_processes"] = top_procs
        except Exception as e:
            logger.warning(f"[SystemMonitor] Process scan failed: {e}")

        return metrics

    @staticmethod
    def _collect_db_metrics(metrics: Dict[str, Any]) -> None:
        """Read connection counters. Raises if the database does not answer."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

            # Reachable from here on; a missing counter stays None (unknown), never a guess.
            cursor.execute("SHOW VARIABLES LIKE 'max_connections'")
            row_max = cursor.fetchone()
            cursor.execute(
                "SHOW STATUS WHERE Variable_name IN ('Threads_connected', 'Slow_queries')"
            )
            status_dict = dict(cursor.fetchall())

            max_conn = int(row_max[1]) if row_max else 0
            threads = status_dict.get("Threads_connected")
            if max_conn > 0 and threads is not None:
                metrics["db_max_connections"] = max_conn
                metrics["db_threads_connected"] = int(threads)
                metrics["db_connection_percent"] = round(
                    int(threads) / max_conn * 100, 1
                )
            metrics["db_slow_queries"] = int(status_dict.get("Slow_queries", 0))

            # Long-running queries (> 10s non-sleep); the account may lack PROCESS privilege.
            try:
                cursor.execute("SHOW FULL PROCESSLIST")
                metrics["db_locked_queries_count"] = len(
                    [
                        p
                        for p in cursor.fetchall()
                        if len(p) >= 6
                        and str(p[4]).lower() != "sleep"
                        and int(p[5] or 0) >= 10
                    ]
                )
            except Exception as e:
                logger.info(f"[SystemMonitor] PROCESSLIST not readable: {e}")

    @classmethod
    def thresholds(cls) -> Dict[str, Dict[str, float]]:
        """Per-metric {warning, critical} thresholds, overridable from settings."""
        out = {k: dict(v) for k, v in DEFAULT_THRESHOLDS.items()}
        overrides = getattr(settings, "SYSTEM_MONITOR_THRESHOLDS", {}) or {}
        for key, vals in overrides.items():
            if key in out and isinstance(vals, dict):
                out[key].update(
                    {
                        k: float(v)
                        for k, v in vals.items()
                        if k in ("warning", "critical")
                    }
                )
        return out

    @classmethod
    def evaluate_threat(
        cls, metrics: Dict[str, Any], threshold: float = None
    ) -> Tuple[bool, List[str], float]:
        """Classify each metric against its warning/critical threshold.

        Returns (is_critical, critical_reasons, highest_metric). Warnings are
        logged but do not alert; a `threshold` arg is accepted for backward
        compatibility and overrides every metric's critical level.
        """
        reasons: List[str] = []
        warnings: List[str] = []
        highest = 0.0
        thresholds = cls.thresholds()
        if threshold is not None:
            thresholds = {
                k: {"warning": v["warning"], "critical": float(threshold)}
                for k, v in thresholds.items()
            }

        def _check(key, value, reason_text):
            nonlocal highest
            if value is None:
                return
            levels = thresholds[key]
            if value >= levels["critical"]:
                reasons.append(f"{reason_text} (critical ≥ {levels['critical']}%)")
                highest = max(highest, value)
            elif value >= levels["warning"]:
                warnings.append(f"{reason_text} (warning ≥ {levels['warning']}%)")

        _check("cpu", metrics["cpu_percent"], f"CPU at {metrics['cpu_percent']}%")
        _check(
            "ram",
            metrics["ram_percent"],
            f"RAM at {metrics['ram_percent']}% ({metrics['ram_used_mb']}MB used of {metrics['ram_total_mb']}MB)",
        )
        _check(
            "disk",
            metrics["disk_percent"],
            f"Disk at {metrics['disk_percent']}% ({metrics['disk_free_gb']}GB free)",
        )
        _check(
            "db",
            metrics.get("db_connection_percent"),
            f"Database connections at {metrics.get('db_display')}",
        )

        # A connectivity failure is its own condition, not a utilization figure,
        # so it does not touch `highest`.
        if metrics.get("db_status") == DB_UNREACHABLE:
            reasons.append(
                f"Database did not respond to {DB_CHECK_ATTEMPTS} attempts "
                f"{DB_RETRY_DELAY_SECONDS}s apart: {metrics.get('db_error')}"
            )

        if warnings:
            logger.warning("[SystemMonitor] WARN: %s", "; ".join(warnings))

        return (len(reasons) > 0), reasons, highest

    @classmethod
    def check_and_alert(
        cls,
        threshold: float = None,
        force: bool = False,
        admin_email: str = None,
        cc_email: str = MANDATORY_CC_EMAIL,
    ) -> Dict[str, Any]:
        """
        Main execution point: Inspects metrics and sends emergency email
        if load >= 95% (with cooldown and CC protection).
        """
        metrics = cls.get_metrics()
        is_critical, reasons, highest = cls.evaluate_threat(
            metrics, threshold=threshold
        )

        result = {
            "is_critical": is_critical,
            "threshold": threshold,
            "highest_metric": highest,
            "reasons": reasons,
            "email_sent": False,
            "cooldown_active": False,
            "metrics": metrics,
        }

        if not is_critical and not force:
            logger.info(
                f"[SystemMonitor] System Healthy — CPU: {metrics['cpu_percent']}%, "
                f"RAM: {metrics['ram_percent']}%, Disk: {metrics['disk_percent']}%, "
                f"DB: {metrics['db_display']}"
            )
            state = cache.get(ACTIVE_ALERT_CACHE_KEY)
            if isinstance(state, dict):
                # Cleared first: a failing save or mail must not repeat every minute.
                cache.delete(ACTIVE_ALERT_CACHE_KEY)
                state["resolved"] = datetime.now()
                cls._save_incident(state)
                result["incident_id"] = state["id"]
                if state["alerted"]:
                    cls._send_recovery_email(metrics, state, admin_email, cc_email)
                    result["recovery_sent"] = True
            return result

        headline = cls._headline(metrics, highest)
        state = cls._track_incident(metrics, reasons, headline) if is_critical else None
        tag = f"[{state['id']}] " if state else ""
        result["incident_id"] = state["id"] if state else None

        # Require N consecutive failed checks before alerting: one blip of high
        # CPU or a single dropped query (surviving the per-check retry) stays
        # silent, and the incident row still records it.
        needed = int(
            getattr(
                settings,
                "SYSTEM_MONITOR_CONSECUTIVE_FAILURES",
                DEFAULT_CONSECUTIVE_FAILURES,
            )
        )
        if state and not force and state["checks"] < needed:
            logger.info(
                "[SystemMonitor] %s %s: %s/%s failed checks, holding alert.",
                state["id"],
                headline,
                state["checks"],
                needed,
            )
            result["pending_checks"] = needed - state["checks"]
            return result

        # Check cooldown to avoid flooding inbox
        now = time.time()
        last_alert_time = cache.get(COOLDOWN_CACHE_KEY, 0)
        time_since_last = now - last_alert_time

        if not force and time_since_last < ALERT_COOLDOWN_SECONDS:
            remaining = int(ALERT_COOLDOWN_SECONDS - time_since_last)
            logger.warning(
                f"[SystemMonitor] ⚠️ Critical condition ({headline}), but alert cooldown active. "
                f"Next alert allowed in {remaining}s."
            )
            result["cooldown_active"] = True
            return result

        # Build and dispatch urgent email
        to_email = (
            admin_email or DEFAULT_ADMIN_EMAIL or "padosiagent@gmail.com"
        ).strip()
        cc_list = [cc_email.strip()] if cc_email else [MANDATORY_CC_EMAIL]

        subject = f"🚨 [CRITICAL ALERT] {tag}PadosiAgent: {headline}"
        # Email shows the strictest critical threshold crossed (or the caller's override).
        shown_threshold = (
            threshold
            if threshold is not None
            else max(t["critical"] for t in cls.thresholds().values())
        )
        html_body = cls._build_emergency_email_html(
            metrics, reasons, highest, shown_threshold, incident=state
        )

        logger.critical(
            f"[SystemMonitor] 🚨 DISPATCHING ALERT ({headline}) to {to_email} (CC: {cc_list}). "
            f"Reasons: {reasons}"
        )

        sent = email_service.send_generic(
            to_email=to_email,
            to_name="PadosiAgent Admin",
            subject=subject,
            html_content=html_body,
            cc_emails=cc_list,
        )

        if sent:
            cache.set(COOLDOWN_CACHE_KEY, now, timeout=ALERT_COOLDOWN_SECONDS + 60)
            if state and not state["alerted"]:
                state["alerted"] = True
                cache.set(ACTIVE_ALERT_CACHE_KEY, state, timeout=7 * 86400)
                if metrics["db_status"] == DB_OK:
                    cls._save_incident(state)
            result["email_sent"] = True

            # Also log into AdminActivityLog
            try:
                from apps.admin_panel.models import AdminActivityLog

                AdminActivityLog.log(
                    action=f"System Alert: {headline}"[:100],
                    model_type="SystemHealth",
                    details={
                        "severity": "CRITICAL_EMERGENCY",
                        "highest_metric": highest,
                        "reasons": reasons,
                        "metrics": metrics,
                        "email_to": to_email,
                        "email_cc": cc_list,
                    },
                )
            except Exception as e:
                logger.warning(
                    f"[SystemMonitor] Failed to log alert in AdminActivityLog: {e}"
                )

        return result

    @staticmethod
    def _headline(metrics: Dict[str, Any], highest: float) -> str:
        """What is wrong, in words. Never a made-up 'server load' percentage."""
        if metrics.get("db_status") == DB_UNREACHABLE:
            return "Database Not Responding"
        return f"Resource Usage at {highest}%"

    @classmethod
    def _track_incident(cls, metrics, reasons, headline) -> Dict[str, Any]:
        """Open the incident on the first failed check, refresh it on later ones.

        The state is kept in the cache because the database may be the thing
        that is down; the row is written whenever the database answers.
        shortcut: an admin "clear cache" during an incident forgets it (the row
        stays DETECTED and no recovery email is sent); key it off the table if
        that ever matters.
        """
        now = datetime.now()  # naive local time, like every other DB datetime here
        state = cache.get(ACTIVE_ALERT_CACHE_KEY)
        if not isinstance(state, dict):
            db_down = metrics.get("db_status") == DB_UNREACHABLE
            state = {
                "id": f"INC-{now:%Y%m%d-%H%M%S}",
                "service": "database" if db_down else "server",
                "title": headline,
                "reasons": reasons,
                "metrics": metrics,
                "first": now,
                "checks": 0,
                "alerted": False,
                "resolved": None,
            }
        state["last"] = now
        state["checks"] += 1
        cache.set(ACTIVE_ALERT_CACHE_KEY, state, timeout=7 * 86400)
        if metrics["db_status"] == DB_OK:  # no point trying while it is unreachable
            cls._save_incident(state)
        return state

    @staticmethod
    def _save_incident(state: Dict[str, Any]) -> None:
        try:
            from apps.admin_panel.models import SystemIncident

            SystemIncident.objects.update_or_create(
                incident_id=state["id"],
                defaults={
                    "service": state["service"],
                    "title": state["title"][:150],
                    "reasons": state["reasons"],
                    "metrics": state["metrics"],
                    "first_detected_at": state["first"],
                    "last_detected_at": state["last"],
                    "resolved_at": state["resolved"],
                    "failed_checks": state["checks"],
                    "alert_sent": state["alerted"],
                },
            )
        except Exception:
            logger.exception(f"[SystemMonitor] Could not save incident {state['id']}")

    @classmethod
    def _send_recovery_email(
        cls, metrics, state, admin_email=None, cc_email=None
    ) -> None:
        """One 'resolved' email when the first healthy check follows an alert."""
        was = f"[{state['id']}] {state['title']}"
        duration = str(state["resolved"] - state["first"]).split(".")[0]
        to_email = (
            admin_email or DEFAULT_ADMIN_EMAIL or "padosiagent@gmail.com"
        ).strip()
        html = (
            "<div style='font-family:Arial,sans-serif;font-size:14px;color:#111827;'>"
            "<h2 style='color:#15803d;'>✅ Resolved: all checks are healthy again</h2>"
            f"<p><strong>Incident:</strong> {escape(was)}<br>"
            f"<strong>First detected:</strong> {state['first']:%Y-%m-%d %H:%M:%S} {settings.TIME_ZONE}<br>"
            f"<strong>Duration:</strong> {duration} ({state['checks']} failed check(s))</p>"
            f"<p><strong>Recovered at:</strong> {escape(metrics['timestamp'])}<br>"
            f"<strong>Server:</strong> {escape(metrics['hostname'])}</p>"
            f"<p>CPU {metrics['cpu_percent']}% &nbsp;|&nbsp; RAM {metrics['ram_percent']}% &nbsp;|&nbsp; "
            f"Disk {metrics['disk_percent']}% &nbsp;|&nbsp; DB connections {escape(metrics['db_display'])}</p>"
            "<p style='color:#6b7280;font-size:12px;'>The database answered this check. "
            "No recovery action was taken by the monitor.</p></div>"
        )
        sent = email_service.send_generic(
            to_email=to_email,
            to_name="PadosiAgent Admin",
            subject=f"✅ [RESOLVED] PadosiAgent: {was}",
            html_content=html,
            cc_emails=[cc_email.strip()] if cc_email else [MANDATORY_CC_EMAIL],
        )
        if not sent:
            logger.error("[SystemMonitor] Recovery email could not be sent.")

    @classmethod
    def _build_emergency_email_html(
        cls,
        metrics: Dict[str, Any],
        reasons: List[str],
        highest: float,
        threshold: float,
        incident: Dict[str, Any] = None,
    ) -> str:
        """
        Construct a responsive, visual, high-urgency HTML email with
        metrics breakdown and actionable step-by-step troubleshooting runbook.
        """
        incident_html = ""
        if incident:
            incident_html = (
                f"<strong>Incident:</strong> {incident['id']} &nbsp;|&nbsp; "
                f"<strong>First detected:</strong> {incident['first']:%Y-%m-%d %H:%M:%S} {settings.TIME_ZONE} "
                f"&nbsp;|&nbsp; <strong>Failed checks so far:</strong> {incident['checks']}<br>"
            )
        reasons_html = "".join(
            [
                f"<li style='margin-bottom:6px;color:#b91c1c;font-weight:600;'>{escape(r)}</li>"
                for r in reasons
            ]
        )

        # Status badge colors
        cpu_color = (
            "#dc2626"
            if metrics["cpu_percent"] >= threshold
            else ("#d97706" if metrics["cpu_percent"] >= 80 else "#16a34a")
        )
        ram_color = (
            "#dc2626"
            if metrics["ram_percent"] >= threshold
            else ("#d97706" if metrics["ram_percent"] >= 80 else "#16a34a")
        )
        disk_color = (
            "#dc2626"
            if metrics["disk_percent"] >= threshold
            else ("#d97706" if metrics["disk_percent"] >= 80 else "#16a34a")
        )
        db_pct = metrics.get("db_connection_percent")
        db_down = metrics.get("db_status") == DB_UNREACHABLE
        if db_pct is None:
            db_color = "#dc2626" if db_down else "#6b7280"
            db_value = "DOWN" if db_down else "N/A"
            db_sub = "connections not measured"
        else:
            db_color = (
                "#dc2626"
                if db_pct >= threshold
                else ("#d97706" if db_pct >= 80 else "#16a34a")
            )
            db_value = f"{db_pct}%"
            db_sub = (
                f"{metrics['db_threads_connected']}/{metrics['db_max_connections']}"
            )
        headline = cls._headline(metrics, highest)

        # Top processes rows
        top_procs_rows = ""
        for p in metrics.get("top_processes", []):
            top_procs_rows += f"""
            <tr>
              <td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;font-family:monospace;font-size:12px;'>{p["pid"]}</td>
              <td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;font-family:monospace;font-size:12px;font-weight:600;'>{p["name"]}</td>
              <td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;font-family:monospace;font-size:12px;color:#dc2626;'>{p["cpu"]}%</td>
              <td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;font-family:monospace;font-size:12px;color:#2563eb;'>{p["mem"]}%</td>
            </tr>
            """

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CRITICAL SERVER LOAD ALERT</title>
</head>
<body style="margin:0;padding:0;background-color:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f3f4f6;padding:24px 12px;">
    <tr><td align="center">
      <table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.1);border-top:6px solid #dc2626;">
        
        <!-- Header banner -->
        <tr>
          <td style="background:#dc2626;padding:24px 32px;color:#ffffff;">
            <div style="font-size:12px;letter-spacing:1px;text-transform:uppercase;font-weight:700;color:#fee2e2;">PadosiAgent System Health Monitor</div>
            <h1 style="margin:8px 0 0;font-size:22px;line-height:1.3;font-weight:800;">🚨 CRITICAL: {headline}</h1>
            <p style="margin:6px 0 0;font-size:14px;color:#fecaca;">The checks listed below failed. Each metric is reported separately; there is no combined load figure.</p>
          </td>
        </tr>

        <!-- Alert Summary Box -->
        <tr>
          <td style="padding:24px 32px 16px;">
            <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:16px 20px;margin-bottom:20px;">
              <h3 style="margin:0 0 8px;color:#991b1b;font-size:15px;">⚠️ What failed (resource threshold: {threshold}%)</h3>
              <ul style="margin:0;padding-left:20px;font-size:13px;line-height:1.6;">
                {reasons_html}
              </ul>
              <div style="margin-top:10px;font-size:12px;color:#7f1d1d;">
                {incident_html}<strong>Server:</strong> {metrics["hostname"]} &nbsp;|&nbsp; <strong>Time:</strong> {metrics["timestamp"]}
              </div>
            </div>

            <!-- Metrics Grid -->
            <h3 style="color:#111827;font-size:15px;margin:0 0 12px;">📊 Current System Metrics:</h3>
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
              <tr>
                <!-- CPU -->
                <td width="24%" style="padding:4px;">
                  <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:11px;color:#6b7280;text-transform:uppercase;font-weight:600;">CPU Load</div>
                    <div style="font-size:22px;font-weight:800;color:{cpu_color};margin:4px 0;">{metrics["cpu_percent"]}%</div>
                    <div style="font-size:11px;color:#9ca3af;">Threshold: {threshold}%</div>
                  </div>
                </td>
                <!-- RAM -->
                <td width="24%" style="padding:4px;">
                  <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:11px;color:#6b7280;text-transform:uppercase;font-weight:600;">RAM Memory</div>
                    <div style="font-size:22px;font-weight:800;color:{ram_color};margin:4px 0;">{metrics["ram_percent"]}%</div>
                    <div style="font-size:11px;color:#9ca3af;">{metrics["ram_used_mb"]}MB used</div>
                  </div>
                </td>
                <!-- Disk -->
                <td width="24%" style="padding:4px;">
                  <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:11px;color:#6b7280;text-transform:uppercase;font-weight:600;">Disk Space</div>
                    <div style="font-size:22px;font-weight:800;color:{disk_color};margin:4px 0;">{metrics["disk_percent"]}%</div>
                    <div style="font-size:11px;color:#9ca3af;">{metrics["disk_free_gb"]}GB free</div>
                  </div>
                </td>
                <!-- DB Connections -->
                <td width="24%" style="padding:4px;">
                  <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:11px;color:#6b7280;text-transform:uppercase;font-weight:600;">DB Conns</div>
                    <div style="font-size:22px;font-weight:800;color:{db_color};margin:4px 0;">{db_value}</div>
                    <div style="font-size:11px;color:#9ca3af;">{db_sub}</div>
                  </div>
                </td>
              </tr>
            </table>

            <!-- Top Processes Table -->
            <div style="margin-bottom:24px;">
              <h4 style="color:#374151;font-size:13px;margin:0 0 8px;">Top Consuming Processes:</h4>
              <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;overflow:hidden;">
                <thead>
                  <tr style="background:#e5e7eb;color:#374151;font-size:11px;text-transform:uppercase;">
                    <th style="padding:6px 10px;text-align:left;">PID</th>
                    <th style="padding:6px 10px;text-align:left;">Process</th>
                    <th style="padding:6px 10px;text-align:left;">CPU %</th>
                    <th style="padding:6px 10px;text-align:left;">RAM %</th>
                  </tr>
                </thead>
                <tbody>
                  {top_procs_rows or '<tr><td colspan="4" style="padding:8px;text-align:center;color:#6b7280;font-size:12px;">No process spikes detected</td></tr>'}
                </tbody>
              </table>
            </div>

            <!-- EMERGENCY RUNBOOK: HOW TO FIX IT -->
            <div style="background:#f8fafc;border:1px solid #cbd5e1;border-radius:8px;padding:20px;margin-bottom:24px;">
              <h2 style="color:#0f172a;font-size:17px;margin:0 0 12px;display:flex;align-items:center;">
                🛠️ What to do
              </h2>
              <p style="font-size:13px;color:#475569;margin:0 0 16px;line-height:1.5;">
                This site runs on shared hosting: there is no root or sudo, and MySQL cannot be restarted from here.
                CPU, RAM and disk above are for the whole shared server, not only this account.
              </p>
              <ol style="font-size:13px;color:#1e293b;line-height:1.7;margin:0;padding-left:20px;">
                <li><strong>Check the site first.</strong> Open the homepage and the admin dashboard. If both load, the database is answering and this was a short connection drop.</li>
                <li><strong>Database not responding:</strong> open cPanel &rarr; phpMyAdmin. If it fails there too, the host's MySQL is down: contact hosting support with the server name and time above. Nothing in the app can fix that.</li>
                <li><strong>Site hanging but database is up:</strong> restart the app from SSH in the app folder: <code>touch tmp/restart.txt</code></li>
                <li><strong>Disk is high:</strong> check <code>logs/</code> and <code>backups/</code> in the app folder and remove old files you recognise. Never delete with wildcards.</li>
                <li>A separate "Resolved" email follows when checks pass again.</li>
              </ol>
            </div>

            <!-- Direct link button -->
            <div style="text-align:center;margin-bottom:16px;">
              <a href="https://padosiagent.com/admin/dashboard/"
                 style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;padding:12px 30px;border-radius:8px;font-size:14px;font-weight:700;">
                Open Admin Dashboard &rsaquo;
              </a>
            </div>

          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;text-align:center;font-size:12px;color:#9ca3af;">
            Automated health alert dispatched to <strong>{DEFAULT_ADMIN_EMAIL}</strong> &nbsp;|&nbsp; CC: <strong>{MANDATORY_CC_EMAIL}</strong><br>
            PadosiAgent Infrastructure &copy; 2026. All rights reserved.
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""
        return html
