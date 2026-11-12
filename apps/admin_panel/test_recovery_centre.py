"""Recovery Centre: allowlisted, audited, Super Admin only, no shell execution.

The view is called directly via RequestFactory (as other admin_panel tests do),
to bypass the admin RBAC middleware's redirect; auth is tested at the view level.
"""

import json
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from apps.admin_panel.models import AdminActivityLog, SystemIncident
from apps.admin_panel.services import recovery
from apps.admin_panel.views.system import recovery_action


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class RecoveryActionViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()

    def _post(self, data=None, super_admin=True, admin_id=1):
        req = self.factory.post("/admin/system/recovery-action/", data=data or {})
        req.session = {}
        with (
            patch(
                "apps.admin_panel.views.system._get_admin_from_session",
                return_value=admin_id,
            ),
            patch("apps.admin_panel.auth.is_super_admin", return_value=super_admin),
        ):
            return recovery_action(req)

    def _json(self, response):
        return json.loads(response.content.decode("utf-8"))

    def test_get_is_rejected(self):
        req = self.factory.get("/admin/system/recovery-action/")
        req.session = {}
        with (
            patch(
                "apps.admin_panel.views.system._get_admin_from_session", return_value=1
            ),
            patch("apps.admin_panel.auth.is_super_admin", return_value=True),
        ):
            res = recovery_action(req)
        self.assertEqual(res.status_code, 405)

    def test_non_super_admin_is_rejected_and_not_audited(self):
        res = self._post({"action": "run_diagnostics"}, super_admin=False)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(AdminActivityLog.objects.count(), 0)

    def test_unknown_action_is_rejected(self):
        res = self._post({"action": "rm -rf /"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self._json(res)["message"], "Unknown action")

    def test_destructive_action_requires_confirmation(self):
        res = self._post({"action": "restart_workers"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self._json(res)["message"], "Confirmation required")

    def test_run_diagnostics_is_audited(self):
        fake = {
            "cpu_percent": 12.3,
            "ram_percent": 20.0,
            "disk_percent": 15.0,
            "ram_used_mb": 1,
            "ram_total_mb": 10,
            "disk_free_gb": 100,
            "db_connection_percent": 5.0,
            "db_display": "5% (8/150)",
            "db_status": "healthy",
            "db_error": None,
        }
        with patch.object(
            recovery.SystemMonitorService, "get_metrics", return_value=fake
        ):
            res = self._post({"action": "run_diagnostics"}, admin_id=42)
        self.assertEqual(res.status_code, 200)
        body = self._json(res)
        self.assertTrue(body["ok"])
        self.assertIn("duration_ms", body)
        self.assertIn("thresholds", body)
        log = AdminActivityLog.objects.get()
        self.assertEqual(log.admin_id, 42)
        self.assertEqual(log.details["action"], "run_diagnostics")
        self.assertTrue(log.details["ok"])

    def test_resolve_incident_closes_row_and_clears_cache(self):
        from datetime import datetime

        from apps.admin_panel.services.system_monitor import ACTIVE_ALERT_CACHE_KEY

        now = datetime.now()
        incident = SystemIncident.objects.create(
            incident_id="INC-TEST-1",
            service="server",
            title="CPU at 97%",
            reasons=["CPU at 97%"],
            metrics={},
            first_detected_at=now,
            last_detected_at=now,
        )
        cache.set(ACTIVE_ALERT_CACHE_KEY, {"id": "INC-TEST-1"}, timeout=60)

        res = self._post(
            {
                "action": "resolve_incident",
                "confirmed": "yes",
                "incident_id": "INC-TEST-1",
            }
        )
        self.assertEqual(res.status_code, 200, res.content)
        incident.refresh_from_db()
        self.assertIsNotNone(incident.resolved_at)
        self.assertIsNone(cache.get(ACTIVE_ALERT_CACHE_KEY))

    def test_resolve_incident_missing_id_fails_cleanly(self):
        res = self._post({"action": "resolve_incident", "confirmed": "yes"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self._json(res)["message"], "incident_id is required")

    def test_restart_workers_touches_restart_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(BASE_DIR=tmp):
                res = self._post({"action": "restart_workers", "confirmed": "yes"})
                self.assertEqual(res.status_code, 200, res.content)
                self.assertTrue((Path(tmp) / "tmp" / "restart.txt").exists())

    def test_test_database_reports_failure(self):
        # Patch the handler directly; patching the shared `connection` object
        # also breaks the AdminActivityLog write (same DB).
        failing = (
            lambda req: {
                "ok": False,
                "message": "Exception: (2013, 'Lost connection')",
            },
            False,
        )
        with patch.dict(recovery.ACTIONS, {"test_database": failing}):
            res = self._post({"action": "test_database"})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(self._json(res)["ok"])
        log = AdminActivityLog.objects.get()
        self.assertFalse(log.details["ok"])
        self.assertIn("2013", log.details["message"])

    def test_verify_backup_status_handles_missing_folder(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(BASE_DIR=tmp):
                res = self._post({"action": "verify_backup_status"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self._json(res)["message"], "backups/ folder is missing")

    def test_available_actions_lists_each_entry(self):
        names = {a["name"] for a in recovery.available_actions()}
        self.assertEqual(names, set(recovery.ACTIONS.keys()))
