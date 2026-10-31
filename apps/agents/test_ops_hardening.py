"""Backups fail loudly, background-job claims are exclusive, bulk commands are guarded."""

import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings

from apps.agents.services import background_jobs

MYSQL_DB = {
    "ENGINE": "django.db.backends.mysql",
    "NAME": "padosi",
    "USER": "padosi_user",
    "PASSWORD": "s3cret-pw",
    "HOST": "127.0.0.1",
    "PORT": "3306",
}


class BackupDatabaseMysqlTests(TestCase):
    def _settings(self, tmpdir):
        fake = MagicMock()
        fake.DATABASES = {"default": MYSQL_DB}
        fake.BASE_DIR = tmpdir
        return fake

    def test_mysqldump_failure_raises_and_never_falls_back_to_dumpdata(self):
        proc = MagicMock()
        proc.stdout = io.BytesIO(b"")
        proc.communicate.return_value = (b"", b"Access denied for user")
        proc.returncode = 2
        mod = "apps.agents.management.commands.backup_database"
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch(f"{mod}.settings", self._settings(tmpdir)),
            patch(f"{mod}.shutil.which", return_value="/usr/bin/mysqldump"),
            patch(f"{mod}.subprocess.Popen", return_value=proc) as popen,
            patch(f"{mod}.Command._backup_dumpdata") as dumpdata,
        ):
            with self.assertRaisesRegex(CommandError, "Access denied"):
                call_command("backup_database", tag="t", stdout=io.StringIO())
            dumpdata.assert_not_called()
            cmd = popen.call_args[0][0]
            self.assertFalse(any("s3cret-pw" in part for part in cmd))
            self.assertEqual(popen.call_args[1]["env"]["MYSQL_PWD"], "s3cret-pw")
            self.assertEqual(list(Path(tmpdir, "backups").iterdir()), [])

    def test_missing_mysqldump_raises(self):
        mod = "apps.agents.management.commands.backup_database"
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch(f"{mod}.settings", self._settings(tmpdir)),
            patch(f"{mod}.shutil.which", return_value=None),
            patch(f"{mod}.os.path.isfile", return_value=False),
            patch(f"{mod}.Command._backup_dumpdata") as dumpdata,
        ):
            with self.assertRaisesRegex(CommandError, "mysqldump not found"):
                call_command("backup_database", stdout=io.StringIO())
            dumpdata.assert_not_called()

    def test_backup_system_passes_password_via_env(self):
        mod = "apps.admin_panel.management.commands.backup_system"
        result = MagicMock(returncode=1, stderr="boom")
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch(f"{mod}.settings", self._settings(tmpdir)),
            patch(f"{mod}.subprocess.run", return_value=result) as run,
        ):
            with self.assertRaises(CommandError):
                call_command("backup_system", stdout=io.StringIO())
            self.assertFalse(any("s3cret-pw" in part for part in run.call_args[0][0]))
            self.assertEqual(run.call_args[1]["env"]["MYSQL_PWD"], "s3cret-pw")


class JobClaimTests(TestCase):
    def tearDown(self):
        cache.delete("bgjobs:last-run:test-job")
        cache.delete("bgjobs:test-claim")

    def test_claim_is_exclusive(self):
        self.assertTrue(background_jobs._claim("bgjobs:test-claim", 1, timeout=60))
        self.assertFalse(background_jobs._claim("bgjobs:test-claim", 1, timeout=60))

    def test_mysql_claim_skipped_when_named_lock_is_held_elsewhere(self):
        cur = MagicMock()
        cur.fetchone.return_value = (0,)  # GET_LOCK timed out: another process holds it
        cursor_cm = MagicMock()
        cursor_cm.__enter__.return_value = cur
        with (
            patch.object(connection, "vendor", "mysql"),
            patch.object(connection, "cursor", return_value=cursor_cm),
        ):
            self.assertFalse(background_jobs._claim("bgjobs:test-claim", 1, timeout=60))
        self.assertIsNone(cache.get("bgjobs:test-claim"))
        self.assertIn("GET_LOCK", cur.execute.call_args_list[0][0][0])

    def test_due_job_starts_once_per_interval(self):
        jobs = (("test-job", 60, lambda: None),)
        with (
            patch.object(background_jobs, "jobs_enabled", return_value=True),
            patch.object(background_jobs, "JOBS", jobs),
            patch.object(background_jobs.threading, "Thread") as thread,
        ):
            self.assertEqual(background_jobs.maybe_run_due_jobs(), ["test-job"])
            self.assertEqual(background_jobs.maybe_run_due_jobs(), [])
        self.assertEqual(thread.call_count, 1)

    def test_daily_backup_job_registered_and_calls_backup_command(self):
        jobs = {name: interval for name, interval, _ in background_jobs.JOBS}
        self.assertEqual(jobs.get("daily-db-backup"), 24 * 60 * 60)
        with patch("django.core.management.call_command") as cc:
            background_jobs._daily_backup_job()
        self.assertEqual(cc.call_args[0][0], "backup_database")
        self.assertEqual(cc.call_args[1]["tag"], "daily")
        self.assertEqual(cc.call_args[1]["retention"], 14)

    def test_daily_backup_failure_is_logged_not_raised(self):
        with (
            patch("django.core.management.call_command", side_effect=CommandError("x")),
            self.assertLogs("apps.agents.services.background_jobs", level="ERROR"),
        ):
            background_jobs._daily_backup_job()


class GuardedCommandTests(TestCase):
    STEPS = (
        "_clear_invalid_user_ids",
        "_merge_duplicate_emails",
        "_collapse_duplicate_profiles",
        "_fix_investment_types",
        "_fill_empty_slugs",
    )

    def _run_repair(self, *args):
        mod = "apps.agents.management.commands.repair_imported_agent_data.Command"
        patches = [patch(f"{mod}.{name}", return_value=0) for name in self.STEPS]
        mocks = [p.start() for p in patches]
        try:
            call_command("repair_imported_agent_data", *args, stdout=io.StringIO())
        finally:
            for p in patches:
                p.stop()
        return {m.call_args[0][0] for m in mocks}

    def test_repair_defaults_to_dry_run(self):
        self.assertEqual(self._run_repair(), {True})

    def test_repair_writes_only_with_apply(self):
        self.assertEqual(self._run_repair("--apply"), {False})

    @override_settings(DEBUG=False)
    def test_seed_homepage_refuses_without_yes(self):
        from apps.home.models.homepage import HeroTrustBadge

        HeroTrustBadge.objects.create(icon="x", label="Kept", order=1)
        with self.assertRaises(CommandError):
            call_command("seed_homepage", stdout=io.StringIO())
        self.assertTrue(HeroTrustBadge.objects.filter(label="Kept").exists())
