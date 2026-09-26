"""
Management command to safely restore the database from a backup file.
Usage:
    python manage.py restore_database --latest --confirm
    python manage.py restore_database --file backups/db_backup_pre_deploy_20260926_150000.sql.gz --confirm
    python manage.py restore_database --latest --dry-run
"""

import os
import gzip
import shutil
import subprocess
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Restores the database from a compressed backup file (.sql.gz, .sqlite3.gz, or .json.gz)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            help='Specific backup filepath to restore from (relative or absolute).',
        )
        parser.add_argument(
            '--latest',
            action='store_true',
            help='Automatically restore from the newest backup file in backups/ directory.',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirmation flag to execute actual database restore.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Verify backup file existence and integrity without modifying the database.',
        )

    def handle(self, *args, **options):
        confirm = options['confirm']
        dry_run = options['dry_run']
        file_arg = options['file']
        use_latest = options['latest']

        backup_dir = Path(settings.BASE_DIR) / 'backups'

        if not file_arg and not use_latest:
            self.stdout.write(self.style.ERROR(
                "Must specify either --file <path> or --latest.\n"
                "Example: python manage.py restore_database --latest --dry-run"
            ))
            return

        if file_arg:
            target_path = Path(file_arg)
            if not target_path.is_absolute():
                target_path = Path(settings.BASE_DIR) / file_arg
        else:
            if not backup_dir.exists():
                self.stdout.write(self.style.ERROR(f"Backup directory not found: {backup_dir}"))
                return
            all_backups = sorted(
                [f for f in backup_dir.glob('db_backup_*') if f.is_file()],
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            if not all_backups:
                self.stdout.write(self.style.ERROR("No backup files found in backups/ directory."))
                return
            target_path = all_backups[0]

        if not target_path.exists():
            self.stdout.write(self.style.ERROR(f"Backup file does not exist: {target_path}"))
            return

        file_size_kb = round(os.path.getsize(target_path) / 1024, 2)
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n=== Database Restore Target ===\n"
            f"File: {target_path.name}\n"
            f"Path: {target_path}\n"
            f"Size: {file_size_kb} KB\n"
        ))

        # Test gzip integrity
        try:
            with gzip.open(target_path, 'rb') as gz_test:
                first_chunk = gz_test.read(1024)
                if not first_chunk:
                    self.stdout.write(self.style.ERROR("Backup file is empty."))
                    return
            self.stdout.write(self.style.SUCCESS("  [OK] Backup archive integrity verified (valid gzip)."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Backup archive is corrupted: {e}"))
            return

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                "\n[DRY RUN] Backup file is valid and ready for restoration.\n"
                "To execute live restore, re-run with --confirm."
            ))
            return

        if not confirm:
            self.stdout.write(self.style.WARNING(
                "\n[SAFETY] Database restore will OVERWRITE current database state.\n"
                "To execute, you must supply the --confirm flag."
            ))
            return

        db_conf = settings.DATABASES.get('default', {})
        engine = db_conf.get('ENGINE', '')

        self.stdout.write(self.style.WARNING("==> Executing database restoration..."))

        if 'mysql' in engine:
            self._restore_mysql(db_conf, target_path)
        elif 'sqlite' in engine:
            self._restore_sqlite(db_conf, target_path)
        else:
            self._restore_json(target_path)

    def _restore_mysql(self, db_conf, target_path):
        name = db_conf.get('NAME', '')
        user = db_conf.get('USER', '')
        password = db_conf.get('PASSWORD', '')
        host = db_conf.get('HOST', '127.0.0.1')
        port = str(db_conf.get('DB_PORT', db_conf.get('PORT', '3306')) or '3306')

        mysql_bin = shutil.which('mysql')
        if not mysql_bin:
            for candidate in ['/usr/bin/mysql', '/usr/local/bin/mysql', '/usr/local/mysql/bin/mysql']:
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    mysql_bin = candidate
                    break

        if not mysql_bin:
            self.stdout.write(self.style.ERROR("mysql client executable not found on system PATH."))
            return

        cmd = [
            mysql_bin,
            f"--host={host}",
            f"--port={port}",
            f"--user={user}",
            name,
        ]
        env = os.environ.copy()
        if password:
            env['MYSQL_PWD'] = password

        try:
            with gzip.open(target_path, 'rb') as f_in:
                proc = subprocess.run(cmd, stdin=f_in, capture_output=True, env=env)
            if proc.returncode == 0:
                self.stdout.write(self.style.SUCCESS("==> [SUCCESS] MySQL database restored successfully!"))
            else:
                stderr = proc.stderr.decode('utf-8', errors='ignore')
                self.stdout.write(self.style.ERROR(f"==> [ERROR] MySQL restore failed: {stderr}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Restore execution error: {e}"))

    def _restore_sqlite(self, db_conf, target_path):
        db_path = Path(db_conf.get('NAME', ''))
        try:
            with gzip.open(target_path, 'rb') as f_in, open(db_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
            self.stdout.write(self.style.SUCCESS("==> [SUCCESS] SQLite database file restored successfully!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"SQLite restore error: {e}"))

    def _restore_json(self, target_path):
        from django.core.management import call_command
        temp_json = target_path.parent / f"restore_temp_{os.getpid()}.json"
        try:
            with gzip.open(target_path, 'rb') as f_in, open(temp_json, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
            call_command('loaddata', str(temp_json))
            self.stdout.write(self.style.SUCCESS("==> [SUCCESS] JSON data restored into database successfully!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"JSON restore error: {e}"))
        finally:
            if temp_json.exists():
                temp_json.unlink()
