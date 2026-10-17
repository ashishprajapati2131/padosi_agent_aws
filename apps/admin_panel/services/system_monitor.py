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

import os
import sys
import time
import socket
import logging
from typing import Dict, Any, List, Tuple

import psutil
from django.conf import settings
from django.db import connection
from django.utils import timezone
from django.core.cache import cache

from apps.agents.services.brevo import email_service

logger = logging.getLogger(__name__)

# Default critical threshold
DEFAULT_CRITICAL_THRESHOLD = 95.0

# Alert cooldown in seconds (15 minutes) to prevent email storms while load is high
ALERT_COOLDOWN_SECONDS = 900
COOLDOWN_CACHE_KEY = "system_load_alert_cooldown_timestamp"

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
            "timestamp": timezone.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
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
            "db_status": "healthy",
            "db_threads_connected": 0,
            "db_max_connections": 150,
            "db_connection_percent": 0.0,
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
            metrics["disk_used_gb"] = round(disk.used / (1024 ** 3), 1)
            metrics["disk_total_gb"] = round(disk.total / (1024 ** 3), 1)
            metrics["disk_free_gb"] = round(disk.free / (1024 ** 3), 1)
        except Exception as e:
            logger.warning(f"[SystemMonitor] Disk check failed: {e}")

        # 4. Database (MySQL) Metrics
        try:
            with connection.cursor() as cursor:
                # Max connections
                cursor.execute("SHOW VARIABLES LIKE 'max_connections'")
                row_max = cursor.fetchone()
                max_conn = int(row_max[1]) if row_max else 151
                metrics["db_max_connections"] = max_conn

                # Thread status
                cursor.execute("SHOW STATUS WHERE Variable_name IN ('Threads_connected', 'Threads_running', 'Slow_queries')")
                status_dict = dict(cursor.fetchall())
                threads_connected = int(status_dict.get("Threads_connected", 1))
                metrics["db_threads_connected"] = threads_connected
                metrics["db_slow_queries"] = int(status_dict.get("Slow_queries", 0))

                # Connection load percentage
                conn_pct = round((threads_connected / max_conn) * 100, 1)
                metrics["db_connection_percent"] = conn_pct

                # Check for long-running / locked queries (> 10s non-sleep)
                try:
                    cursor.execute("SHOW FULL PROCESSLIST")
                    procs = cursor.fetchall()
                    locked = [
                        p for p in procs
                        if len(p) >= 6 and str(p[4]).lower() != "sleep" and int(p[5] or 0) >= 10
                    ]
                    metrics["db_locked_queries_count"] = len(locked)
                except Exception:
                    pass
        except Exception as e:
            metrics["db_status"] = f"CRITICAL_UNREACHABLE: {e}"
            metrics["db_connection_percent"] = 100.0
            logger.error(f"[SystemMonitor] MySQL status check failed: {e}")

        # 5. Top 5 CPU/Memory consuming processes
        try:
            procs_list = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                try:
                    info = p.info
                    procs_list.append({
                        "pid": info["pid"],
                        "name": info["name"],
                        "cpu": round(info["cpu_percent"] or 0.0, 1),
                        "mem": round(info["memory_percent"] or 0.0, 1),
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Sort by CPU desc
            top_procs = sorted(procs_list, key=lambda x: (x["cpu"], x["mem"]), reverse=True)[:5]
            metrics["top_processes"] = top_procs
        except Exception as e:
            logger.warning(f"[SystemMonitor] Process scan failed: {e}")

        return metrics

    @classmethod
    def evaluate_threat(cls, metrics: Dict[str, Any], threshold: float = DEFAULT_CRITICAL_THRESHOLD) -> Tuple[bool, List[str], float]:
        """
        Evaluate if any resource has crossed the critical threshold.
        Returns (is_critical, alarm_reasons_list, highest_metric_value).
        """
        reasons = []
        highest = 0.0

        # CPU check
        if metrics["cpu_percent"] >= threshold:
            reasons.append(f"CPU Utilization is at {metrics['cpu_percent']}% (Threshold: {threshold}%)")
            highest = max(highest, metrics["cpu_percent"])

        # RAM check
        if metrics["ram_percent"] >= threshold:
            reasons.append(f"RAM / Memory Usage is at {metrics['ram_percent']}% ({metrics['ram_used_mb']}MB used of {metrics['ram_total_mb']}MB)")
            highest = max(highest, metrics["ram_percent"])

        # Disk check
        if metrics["disk_percent"] >= threshold:
            reasons.append(f"Root Disk Space is at {metrics['disk_percent']}% ({metrics['disk_free_gb']}GB free left)")
            highest = max(highest, metrics["disk_percent"])

        # DB Connection Saturation
        if metrics["db_connection_percent"] >= threshold:
            reasons.append(f"Database Connection Pool at {metrics['db_connection_percent']}% ({metrics['db_threads_connected']}/{metrics['db_max_connections']} connections)")
            highest = max(highest, metrics["db_connection_percent"])

        if "CRITICAL" in str(metrics.get("db_status", "")):
            reasons.append(f"Database is down or failing to respond: {metrics.get('db_status')}")
            highest = max(highest, 100.0)

        is_critical = len(reasons) > 0
        return is_critical, reasons, highest

    @classmethod
    def check_and_alert(
        cls,
        threshold: float = DEFAULT_CRITICAL_THRESHOLD,
        force: bool = False,
        admin_email: str = None,
        cc_email: str = MANDATORY_CC_EMAIL,
    ) -> Dict[str, Any]:
        """
        Main execution point: Inspects metrics and sends emergency email
        if load >= 95% (with cooldown and CC protection).
        """
        metrics = cls.get_metrics()
        is_critical, reasons, highest = cls.evaluate_threat(metrics, threshold=threshold)

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
                f"DB: {metrics['db_connection_percent']}%"
            )
            return result

        # Check cooldown to avoid flooding inbox
        now = time.time()
        last_alert_time = cache.get(COOLDOWN_CACHE_KEY, 0)
        time_since_last = now - last_alert_time

        if not force and time_since_last < ALERT_COOLDOWN_SECONDS:
            remaining = int(ALERT_COOLDOWN_SECONDS - time_since_last)
            logger.warning(
                f"[SystemMonitor] ⚠️ Critical load detected ({highest}%), but alert cooldown active. "
                f"Next alert allowed in {remaining}s."
            )
            result["cooldown_active"] = True
            return result

        # Build and dispatch urgent email
        to_email = (admin_email or DEFAULT_ADMIN_EMAIL or "padosiagent@gmail.com").strip()
        cc_list = [cc_email.strip()] if cc_email else [MANDATORY_CC_EMAIL]

        subject = f"🚨 [CRITICAL ALERT] PadosiAgent System Load Exceeded 95% ({highest}%) — Action Required"
        html_body = cls._build_emergency_email_html(metrics, reasons, highest, threshold)

        logger.critical(
            f"[SystemMonitor] 🚨 DISPATCHING EMERGENCY 95% LOAD ALERT to {to_email} (CC: {cc_list}). "
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
            result["email_sent"] = True

            # Also log into AdminActivityLog
            try:
                from apps.admin_panel.models import AdminActivityLog
                AdminActivityLog.log(
                    action=f"System Load Alert: {highest}%",
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
                logger.warning(f"[SystemMonitor] Failed to log alert in AdminActivityLog: {e}")

        return result

    @classmethod
    def _build_emergency_email_html(
        cls,
        metrics: Dict[str, Any],
        reasons: List[str],
        highest: float,
        threshold: float,
    ) -> str:
        """
        Construct a responsive, visual, high-urgency HTML email with
        metrics breakdown and actionable step-by-step troubleshooting runbook.
        """
        reasons_html = "".join([f"<li style='margin-bottom:6px;color:#b91c1c;font-weight:600;'>{r}</li>" for r in reasons])

        # Status badge colors
        cpu_color = "#dc2626" if metrics["cpu_percent"] >= threshold else ("#d97706" if metrics["cpu_percent"] >= 80 else "#16a34a")
        ram_color = "#dc2626" if metrics["ram_percent"] >= threshold else ("#d97706" if metrics["ram_percent"] >= 80 else "#16a34a")
        disk_color = "#dc2626" if metrics["disk_percent"] >= threshold else ("#d97706" if metrics["disk_percent"] >= 80 else "#16a34a")
        db_color = "#dc2626" if metrics["db_connection_percent"] >= threshold else ("#d97706" if metrics["db_connection_percent"] >= 80 else "#16a34a")

        # Top processes rows
        top_procs_rows = ""
        for p in metrics.get("top_processes", []):
            top_procs_rows += f"""
            <tr>
              <td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;font-family:monospace;font-size:12px;'>{p['pid']}</td>
              <td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;font-family:monospace;font-size:12px;font-weight:600;'>{p['name']}</td>
              <td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;font-family:monospace;font-size:12px;color:#dc2626;'>{p['cpu']}%</td>
              <td style='padding:6px 10px;border-bottom:1px solid #e5e7eb;font-family:monospace;font-size:12px;color:#2563eb;'>{p['mem']}%</td>
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
            <h1 style="margin:8px 0 0;font-size:22px;line-height:1.3;font-weight:800;">🚨 CRITICAL: Server Load Reached {highest}%</h1>
            <p style="margin:6px 0 0;font-size:14px;color:#fecaca;">Proactive crash warning: system resources are near exhaustion. Please act immediately to prevent website downtime.</p>
          </td>
        </tr>

        <!-- Alert Summary Box -->
        <tr>
          <td style="padding:24px 32px 16px;">
            <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:16px 20px;margin-bottom:20px;">
              <h3 style="margin:0 0 8px;color:#991b1b;font-size:15px;">⚠️ Critical Threshold Crossed (>= {threshold}%)</h3>
              <ul style="margin:0;padding-left:20px;font-size:13px;line-height:1.6;">
                {reasons_html}
              </ul>
              <div style="margin-top:10px;font-size:12px;color:#7f1d1d;">
                <strong>Server:</strong> {metrics['hostname']} &nbsp;|&nbsp; <strong>Time:</strong> {metrics['timestamp']}
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
                    <div style="font-size:22px;font-weight:800;color:{cpu_color};margin:4px 0;">{metrics['cpu_percent']}%</div>
                    <div style="font-size:11px;color:#9ca3af;">Threshold: {threshold}%</div>
                  </div>
                </td>
                <!-- RAM -->
                <td width="24%" style="padding:4px;">
                  <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:11px;color:#6b7280;text-transform:uppercase;font-weight:600;">RAM Memory</div>
                    <div style="font-size:22px;font-weight:800;color:{ram_color};margin:4px 0;">{metrics['ram_percent']}%</div>
                    <div style="font-size:11px;color:#9ca3af;">{metrics['ram_used_mb']}MB used</div>
                  </div>
                </td>
                <!-- Disk -->
                <td width="24%" style="padding:4px;">
                  <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:11px;color:#6b7280;text-transform:uppercase;font-weight:600;">Disk Space</div>
                    <div style="font-size:22px;font-weight:800;color:{disk_color};margin:4px 0;">{metrics['disk_percent']}%</div>
                    <div style="font-size:11px;color:#9ca3af;">{metrics['disk_free_gb']}GB free</div>
                  </div>
                </td>
                <!-- DB Connections -->
                <td width="24%" style="padding:4px;">
                  <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px;text-align:center;">
                    <div style="font-size:11px;color:#6b7280;text-transform:uppercase;font-weight:600;">DB Conns</div>
                    <div style="font-size:22px;font-weight:800;color:{db_color};margin:4px 0;">{metrics['db_connection_percent']}%</div>
                    <div style="font-size:11px;color:#9ca3af;">{metrics['db_threads_connected']}/{metrics['db_max_connections']}</div>
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
                🛠️ EMERGENCY RUNBOOK: How to Fix This Load Immediately
              </h2>
              <p style="font-size:13px;color:#475569;margin:0 0 16px;line-height:1.5;">
                Follow these exact steps in order of priority based on which resource is exhausted:
              </p>

              <!-- Step 1: CPU Fix -->
              <div style="margin-bottom:14px;">
                <div style="font-size:13px;font-weight:700;color:#1e293b;">1️⃣ If CPU is High (>= 95%): Restart Application Workers</div>
                <div style="background:#1e293b;color:#38bdf8;padding:8px 12px;border-radius:6px;font-family:monospace;font-size:12px;margin:6px 0;">
                  sudo systemctl restart gunicorn &nbsp;# Or: touch tmp/restart.txt (cPanel)
                </div>
                <div style="font-size:12px;color:#64748b;">This instantly terminates hanging Python threads and resets worker concurrency.</div>
              </div>

              <!-- Step 2: RAM Fix -->
              <div style="margin-bottom:14px;">
                <div style="font-size:13px;font-weight:700;color:#1e293b;">2️⃣ If RAM / Memory is High (>= 95%): Flush Caches & Reclaim Buffer</div>
                <div style="background:#1e293b;color:#38bdf8;padding:8px 12px;border-radius:6px;font-family:monospace;font-size:12px;margin:6px 0;">
                  python manage.py clear_cache<br>
                  redis-cli FLUSHALL &nbsp;# If Redis is configured<br>
                  sync; echo 3 | sudo tee /proc/sys/vm/drop_caches
                </div>
                <div style="font-size:12px;color:#64748b;">Flushes cached query results and reclaims kernel disk buffers.</div>
              </div>

              <!-- Step 3: MySQL Fix -->
              <div style="margin-bottom:14px;">
                <div style="font-size:13px;font-weight:700;color:#1e293b;">3️⃣ If Database Connections or Queries are High: Kill Blocked Queries</div>
                <div style="background:#1e293b;color:#38bdf8;padding:8px 12px;border-radius:6px;font-family:monospace;font-size:12px;margin:6px 0;">
                  mysql -u root -p -e "SHOW FULL PROCESSLIST;"<br>
                  # Find any query with Time &gt; 10s and kill it:<br>
                  mysql -u root -p -e "KILL &lt;PROCESS_ID&gt;;"
                </div>
                <div style="font-size:12px;color:#64748b;">If MySQL is hanging, restart MySQL cleanly: <code>sudo systemctl restart mysql</code></div>
              </div>

              <!-- Step 4: Disk Fix -->
              <div style="margin-bottom:8px;">
                <div style="font-size:13px;font-weight:700;color:#1e293b;">4️⃣ If Disk is Full (>= 95%): Clean System Logs & Temp Dumps</div>
                <div style="background:#1e293b;color:#38bdf8;padding:8px 12px;border-radius:6px;font-family:monospace;font-size:12px;margin:6px 0;">
                  sudo journalctl --vacuum-size=100M<br>
                  rm -rf cache/* /tmp/* logs/*.log.old
                </div>
              </div>
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
