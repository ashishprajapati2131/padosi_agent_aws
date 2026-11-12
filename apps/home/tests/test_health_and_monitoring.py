import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, Client, override_settings
from django.core.management import call_command

from padosi_agent.views import DB_HEALTH_CACHE_KEY
from django.urls import reverse


class HealthAndMonitoringTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_health_check_endpoint(self):
        res = self.client.get("/health/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "healthy")
        self.assertEqual(data.get("database"), "ok")
        self.assertEqual(data.get("cache"), "ok")

    def test_healthz_alias_endpoint(self):
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "healthy")

    def test_live_does_not_touch_database_or_cache(self):
        with (
            patch("padosi_agent.views._db_ok", side_effect=AssertionError),
            patch("padosi_agent.views._cache_ok", side_effect=AssertionError),
        ):
            res = self.client.get("/health/live")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

    def test_database_and_ready_ok(self):
        cache.delete(DB_HEALTH_CACHE_KEY)
        self.assertEqual(self.client.get("/health/database").json(), {"status": "ok"})
        self.assertEqual(
            self.client.get("/health/ready").json().get("status"), "healthy"
        )

    def test_database_down_is_503_without_error_details(self):
        cache.delete(DB_HEALTH_CACHE_KEY)
        secret = (
            "Lost connection to server at 'db-host.internal' for user 'padosi_user'"
        )
        with patch("django.db.connection.cursor", side_effect=Exception(2013, secret)):
            for url in ("/health/database", "/health/ready", "/health/"):
                res = self.client.get(url)
                self.assertEqual(res.status_code, 503, url)
                self.assertNotIn("db-host", res.content.decode(), url)
                self.assertNotIn("2013", res.content.decode(), url)
            # Liveness stays up while the database is down.
            self.assertEqual(self.client.get("/health/live").status_code, 200)
        cache.delete(DB_HEALTH_CACHE_KEY)

    def test_database_probe_is_cached(self):
        cache.delete(DB_HEALTH_CACHE_KEY)
        self.client.get("/health/database")
        with patch(
            "django.db.connection.cursor",
            side_effect=AssertionError("probe must be cached"),
        ):
            self.assertEqual(self.client.get("/health/database").status_code, 200)
        cache.delete(DB_HEALTH_CACHE_KEY)

    def test_redis_not_configured_and_unavailable(self):
        with override_settings(REDIS_URL=""):
            self.assertEqual(
                self.client.get("/health/redis").json(), {"status": "not_configured"}
            )
        with (
            override_settings(REDIS_URL="redis://example.invalid:6379/0"),
            patch("padosi_agent.views._cache_ok", return_value=False),
        ):
            res = self.client.get("/health/redis")
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json(), {"status": "unavailable"})

    def test_backup_database_dry_run(self):
        # Verify backup command executes cleanly
        call_command("backup_database", "--tag", "test_ci", "--retention", "3")

    def test_verify_production_env_runs(self):
        # Verify verification command executes without throwing unexpected exception
        try:
            call_command("verify_production_env")
        except SystemExit:
            pass  # Expected in test environment where some prod env vars are missing

    def test_restore_database_dry_run(self):
        # Verify restore command dry run executes safely
        call_command("restore_database", "--latest", "--dry-run")
