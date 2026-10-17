import time
from django.core.management.base import BaseCommand
from apps.admin_panel.services.system_monitor import SystemMonitorService, DEFAULT_CRITICAL_THRESHOLD, MANDATORY_CC_EMAIL


class Command(BaseCommand):
    help = "Check server load (CPU, RAM, Disk, MySQL). If >= 95%, triggers emergency alert email with recovery runbook to admin + CC."

    def add_arguments(self, parser):
        parser.add_argument(
            "--threshold",
            type=float,
            default=DEFAULT_CRITICAL_THRESHOLD,
            help="Critical percentage threshold (default: 95.0)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force sending the alert email even if metrics are below threshold (for testing delivery to admin and CC).",
        )
        parser.add_argument(
            "--daemon",
            action="store_true",
            help="Run continuously as a standing background monitoring daemon.",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Check interval in seconds when running with --daemon (default: 60s).",
        )
        parser.add_argument(
            "--cc",
            type=str,
            default=MANDATORY_CC_EMAIL,
            help="CC email recipient (default: parth.ramanujj@gmail.com).",
        )
        parser.add_argument(
            "--preview",
            action="store_true",
            help="Render and save the emergency alert HTML email locally and open it in browser.",
        )

    def handle(self, *args, **options):
        threshold = options["threshold"]
        force = options["force"]
        daemon = options["daemon"]
        interval = options["interval"]
        cc_email = options["cc"]
        preview = options.get("preview")

        if preview:
            from pathlib import Path
            import webbrowser
            metrics = SystemMonitorService.get_metrics()
            html = SystemMonitorService._build_emergency_email_html(
                metrics,
                reasons=[
                    f"SIMULATED: CPU Load reached {max(metrics['cpu_percent'], 96.5)}% (Threshold: {threshold}%)",
                    f"SIMULATED: RAM Memory reached {max(metrics['ram_percent'], 97.2)}% (Threshold: {threshold}%)",
                ],
                highest=97.2,
                threshold=threshold,
            )
            preview_file = Path("alert_email_preview.html").resolve()
            preview_file.write_text(html, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"[PREVIEW] Alert email saved to: {preview_file}"))
            webbrowser.open(preview_file.as_uri())
            return

        self.stdout.write(f"[Monitor] Starting system load inspection (Threshold: {threshold}%, CC: {cc_email})...")

        if not daemon:
            res = SystemMonitorService.check_and_alert(threshold=threshold, force=force, cc_email=cc_email)
            m = res["metrics"]
            self.stdout.write(
                f"Metrics: CPU={m['cpu_percent']}%, RAM={m['ram_percent']}%, "
                f"Disk={m['disk_percent']}%, DB Conns={m['db_connection_percent']}%"
            )
            if res["email_sent"]:
                self.stdout.write(self.style.SUCCESS(f"[ALERT SENT] Emergency alert email sent successfully! (CC: {cc_email})"))
            elif res["cooldown_active"]:
                self.stdout.write(self.style.WARNING("[COOLDOWN] Load is critical, but alert cooldown is active."))
            elif res["is_critical"]:
                self.stdout.write(self.style.ERROR("[ALERT FAILED] Critical load detected, but email dispatch failed."))
            else:
                self.stdout.write(self.style.SUCCESS("[OK] System is healthy (all metrics below threshold)."))
            return

        self.stdout.write(self.style.SUCCESS(f"Running as background monitoring daemon (interval: {interval}s). Press Ctrl+C to stop."))
        while True:
            try:
                res = SystemMonitorService.check_and_alert(threshold=threshold, force=False, cc_email=cc_email)
                m = res["metrics"]
                status = "ALERT SENT" if res["email_sent"] else ("COOLDOWN" if res["cooldown_active"] else "OK")
                self.stdout.write(
                    f"[{m['timestamp']}] CPU: {m['cpu_percent']}% | RAM: {m['ram_percent']}% | "
                    f"Disk: {m['disk_percent']}% | DB: {m['db_connection_percent']}% -> {status}"
                )
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Monitor error: {e}"))
            time.sleep(interval)
