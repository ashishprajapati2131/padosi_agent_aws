"""System monitor: a failed DB measurement is never shown as 0% or 100%.

Regression for the 2026-11-11 alert ("DB connections 100% (0/150)", "Server
Load 100%") caused by one MySQL 2013 on the monitor's own connection.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.admin_panel.models import SystemIncident
from apps.admin_panel.services import system_monitor as sm
from apps.admin_panel.services.system_monitor import SystemMonitorService as Svc

LOST = Exception(2013, "Lost connection to server during query")


def _db(threads, max_conn):
    def collect(metrics):
        metrics["db_threads_connected"] = threads
        metrics["db_max_connections"] = max_conn
        metrics["db_connection_percent"] = round(threads / max_conn * 100, 1)

    return collect


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    # Keep the existing tests on "alert on first failed check"; the gating
    # has its own test below.
    SYSTEM_MONITOR_CONSECUTIVE_FAILURES=1,
)
@patch.object(sm.time, "sleep", lambda s: None)
@patch.object(sm.connection, "close", lambda: None)
class SystemMonitorTests(TestCase):
    def setUp(self):
        cache.clear()

    def _metrics(self, collect):
        with patch.object(Svc, "_collect_db_metrics", side_effect=collect) as m:
            metrics = Svc.get_metrics()
        return metrics, m

    def test_zero_connections_is_zero_percent(self):
        metrics, _ = self._metrics(_db(0, 150))
        self.assertEqual(metrics["db_connection_percent"], 0.0)
        self.assertEqual(metrics["db_display"], "0.0% (0/150)")
        self.assertFalse(
            Svc.evaluate_threat(metrics)[0]
            and "Database" in str(Svc.evaluate_threat(metrics)[1])
        )

    def test_unreachable_db_has_no_utilization(self):
        metrics, m = self._metrics(LOST)
        self.assertEqual(m.call_count, sm.DB_CHECK_ATTEMPTS)
        self.assertEqual(metrics["db_status"], sm.DB_UNREACHABLE)
        self.assertIsNone(metrics["db_connection_percent"])
        self.assertIsNone(metrics["db_threads_connected"])
        self.assertIsNone(metrics["db_max_connections"])
        self.assertEqual(metrics["db_display"], "UNAVAILABLE")
        self.assertIn("2013", metrics["db_error"])

        critical, reasons, highest = Svc.evaluate_threat(metrics)
        db_reasons = [r for r in reasons if "Database" in r]
        self.assertTrue(critical)
        self.assertEqual(len(db_reasons), 1)
        self.assertIn("2013", db_reasons[0])
        self.assertNotIn("100", db_reasons[0])
        self.assertNotEqual(highest, 100.0)
        self.assertEqual(Svc._headline(metrics, highest), "Database Not Responding")

        html = Svc._build_emergency_email_html(metrics, reasons, highest, 95.0)
        self.assertIn(">DOWN<", html)
        self.assertNotIn("0/150", html)
        self.assertNotIn("Server Load Reached", html)
        for unsafe in ("FLUSHALL", "rm -rf", "sudo systemctl", "KILL"):
            self.assertNotIn(unsafe, html)

    def test_single_dropped_connection_is_not_an_outage(self):
        calls = []

        def flaky(metrics):
            calls.append(1)
            if len(calls) == 1:
                raise LOST
            _db(12, 150)(metrics)

        metrics, _ = self._metrics(flaky)
        self.assertEqual(metrics["db_status"], sm.DB_OK)
        self.assertEqual(metrics["db_connection_percent"], 8.0)
        self.assertNotIn("Database", str(Svc.evaluate_threat(metrics)[1]))

    def test_saturation_is_reported_from_real_numbers(self):
        metrics, _ = self._metrics(_db(145, 150))
        reasons = Svc.evaluate_threat(metrics)[1]
        self.assertTrue(
            any("Database connections at 96.7% (145/150)" in r for r in reasons)
        )

    def test_per_metric_thresholds_distinguish_warning_from_critical(self):
        base = self._metrics(_db(5, 150))[0]
        # CPU 82 is a warning (≥75 default) but not critical (<95) → no alert.
        warn = self._quiet(dict(base), cpu_percent=82.0)
        critical, reasons, highest = Svc.evaluate_threat(warn)
        self.assertFalse(critical)
        self.assertEqual(reasons, [])
        self.assertEqual(highest, 0.0)

        # DB saturation uses its own ceiling (90% default), not the CPU/RAM/disk 95%.
        hot = self._quiet(dict(base))
        hot.update({"db_connection_percent": 92.0, "db_display": "92.0% (138/150)"})
        critical, reasons, highest = Svc.evaluate_threat(hot)
        self.assertTrue(critical)
        self.assertEqual(highest, 92.0)
        self.assertTrue(any("Database connections" in r for r in reasons))

    @override_settings(SYSTEM_MONITOR_THRESHOLDS={"cpu": {"critical": 60.0}})
    def test_thresholds_can_be_overridden_from_settings(self):
        base = self._quiet(self._metrics(_db(5, 150))[0], cpu_percent=70.0)
        self.assertTrue(Svc.evaluate_threat(base)[0])

    @override_settings(SYSTEM_MONITOR_CONSECUTIVE_FAILURES=3)
    def test_alert_waits_for_consecutive_failed_checks(self):
        cache.clear()
        base = self._metrics(_db(5, 150))[0]
        hot = self._quiet(dict(base), cpu_percent=97.0)
        with (
            patch.object(sm.email_service, "send_generic", return_value=True) as send,
            patch("apps.admin_panel.models.AdminActivityLog.log"),
            patch.object(Svc, "get_metrics", return_value=hot),
        ):
            first = Svc.check_and_alert()
            self.assertFalse(first["email_sent"])
            self.assertEqual(first["pending_checks"], 2)
            send.assert_not_called()
            # Incident is still recorded from the first failed check.
            self.assertEqual(SystemIncident.objects.get().failed_checks, 1)

            self.assertFalse(Svc.check_and_alert()["email_sent"])
            send.assert_not_called()

            third = Svc.check_and_alert()
        self.assertTrue(third["email_sent"])
        self.assertEqual(SystemIncident.objects.get().failed_checks, 3)

        # One healthy check clears the pending counter: a later failure starts over.
        with patch.object(Svc, "get_metrics", return_value=self._quiet(dict(base))):
            Svc.check_and_alert()
        with (
            patch.object(sm.email_service, "send_generic", return_value=True) as send,
            patch("apps.admin_panel.models.AdminActivityLog.log"),
            patch.object(Svc, "get_metrics", return_value=hot),
        ):
            self.assertFalse(Svc.check_and_alert()["email_sent"])
            send.assert_not_called()

    def test_reachable_but_counters_missing_is_unknown(self):
        metrics, _ = self._metrics(lambda metrics: None)
        self.assertEqual(metrics["db_status"], sm.DB_OK)
        self.assertIsNone(metrics["db_connection_percent"])
        self.assertEqual(metrics["db_display"], "UNAVAILABLE")
        self.assertIn(">N/A<", Svc._build_emergency_email_html(metrics, [], 0.0, 95.0))

    def _quiet(self, metrics, **overrides):
        """Host numbers under test control (the dev machine's real load must not decide)."""
        metrics.update({"cpu_percent": 10.0, "ram_percent": 10.0, "disk_percent": 10.0})
        metrics.update(overrides)
        return metrics

    def test_alert_dedup_then_one_recovery_email(self):
        down = self._quiet(self._metrics(LOST)[0])
        up = self._quiet(self._metrics(_db(5, 150))[0])
        with (
            patch.object(sm.email_service, "send_generic", return_value=True) as send,
            patch("apps.admin_panel.models.AdminActivityLog.log"),
        ):
            with patch.object(Svc, "get_metrics", return_value=down):
                self.assertTrue(Svc.check_and_alert()["email_sent"])
                second = Svc.check_and_alert()
                self.assertTrue(second["cooldown_active"])
                self.assertFalse(second["email_sent"])
            self.assertEqual(send.call_count, 1)
            self.assertIn("Database Not Responding", send.call_args.kwargs["subject"])
            incident_id = second["incident_id"]
            self.assertIn(incident_id, send.call_args.kwargs["subject"])
            self.assertIn(incident_id, send.call_args.kwargs["html_content"])
            # The database is the thing that is down: nothing is written to it yet.
            self.assertEqual(SystemIncident.objects.count(), 0)

            with patch.object(Svc, "get_metrics", return_value=up):
                self.assertTrue(Svc.check_and_alert().get("recovery_sent"))
                self.assertFalse(Svc.check_and_alert().get("recovery_sent"))
            self.assertEqual(send.call_count, 2)
            self.assertIn("RESOLVED", send.call_args.kwargs["subject"])
            self.assertIn(incident_id, send.call_args.kwargs["subject"])

        # One row for the whole outage, written once the database answered.
        incident = SystemIncident.objects.get()
        self.assertEqual(incident.incident_id, incident_id)
        self.assertEqual(incident.service, "database")
        self.assertEqual(incident.status, "RESOLVED")
        self.assertEqual(incident.failed_checks, 2)
        self.assertTrue(incident.alert_sent)
        self.assertIn("2013", incident.reasons[0])
        self.assertLessEqual(incident.first_detected_at, incident.resolved_at)

    def test_resource_incident_is_one_row_from_detection_to_recovery(self):
        base = self._metrics(_db(5, 150))[0]
        hot = self._quiet(dict(base), cpu_percent=97.0)
        with (
            patch.object(sm.email_service, "send_generic", return_value=False) as send,
            patch.object(Svc, "get_metrics", return_value=hot),
        ):
            Svc.check_and_alert()
            incident = SystemIncident.objects.get()
            self.assertEqual(
                (incident.status, incident.service), ("DETECTED", "server")
            )
            Svc.check_and_alert()
        incident = SystemIncident.objects.get()
        self.assertEqual(incident.failed_checks, 2)
        self.assertFalse(incident.alert_sent)  # the email failed, and the row says so

        with (
            patch.object(sm.email_service, "send_generic") as send,
            patch.object(Svc, "get_metrics", return_value=self._quiet(dict(base))),
        ):
            result = Svc.check_and_alert()
        self.assertEqual(SystemIncident.objects.get().status, "RESOLVED")
        # No alert reached anyone, so no "resolved" email either.
        self.assertFalse(result.get("recovery_sent"))
        send.assert_not_called()

    def test_cpu_ram_disk_thresholds(self):
        base = self._metrics(_db(5, 150))[0]
        for key, word in (
            ("cpu_percent", "CPU"),
            ("ram_percent", "RAM"),
            ("disk_percent", "Disk"),
        ):
            metrics = self._quiet(dict(base), **{key: 97.0})
            critical, reasons, highest = Svc.evaluate_threat(metrics)
            self.assertTrue(critical)
            self.assertEqual(highest, 97.0)
            self.assertEqual(len(reasons), 1)
            self.assertIn(word, reasons[0])
        self.assertFalse(Svc.evaluate_threat(self._quiet(dict(base)))[0])
