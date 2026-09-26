import os
import gzip
import shutil
import subprocess
import datetime
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Creates an automated timestamped backup of the database before migrations or on schedule."

    def add_arguments(self, parser):
        parser.add_argument(
            '--tag',
            type=str,
            default='manual',
            help='Tag prefix for the backup file (e.g. pre_deploy, hourly, daily)',
        )
        parser.add_argument(
            '--retention',
            type=int,
            default=7,
            help='Number of most recent backups to retain (older ones are pruned). Default is 7.',
        )

    def handle(self, *args, **options):
        tag = options['tag']
        retention = options['retention']
        db_conf = settings.DATABASES.get('default', {})
        engine = db_conf.get('ENGINE', '')

        backup_dir = Path(settings.BASE_DIR) / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)

        now_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        base_filename = f"db_backup_{tag}_{now_str}"

        self.stdout.write(f"==> Initiating automated database backup (Tag: {tag})...")

        success = False
        target_path = None

        if 'mysql' in engine:
            success, target_path = self._backup_mysql(db_conf, backup_dir, base_filename)
        elif 'sqlite' in engine:
            success, target_path = self._backup_sqlite(db_conf, backup_dir, base_filename)
        else:
            self.stdout.write(self.style.WARNING(f"Engine {engine} using Django dumpdata fallback."))
            success, target_path = self._backup_dumpdata(backup_dir, base_filename)

        if success and target_path:
            file_size_kb = round(os.path.getsize(target_path) / 1024, 2)
            self.stdout.write(self.style.SUCCESS(
                f"==> [SUCCESS] Database backup created: {target_path.name} ({file_size_kb} KB)"
            ))
            self._prune_old_backups(backup_dir, retention)
        else:
            self.stdout.write(self.style.ERROR("==> [ERROR] Database backup could not be completed."))

    def _backup_mysql(self, db_conf, backup_dir, base_filename):
        target_file = backup_dir / f"{base_filename}.sql.gz"
        name = db_conf.get('NAME', '')
        user = db_conf.get('USER', '')
        password = db_conf.get('PASSWORD', '')
        host = db_conf.get('HOST', '127.0.0.1')
        port = str(db_conf.get('DB_PORT', db_conf.get('PORT', '3306')) or '3306')

        mysqldump_bin = shutil.which('mysqldump')
        if not mysqldump_bin:
            # Common paths on GoDaddy / Linux cPanel
            for candidate in ['/usr/bin/mysqldump', '/usr/local/bin/mysqldump', '/usr/local/mysql/bin/mysqldump']:
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    mysqldump_bin = candidate
                    break

        if mysqldump_bin and name:
            cmd = [
                mysqldump_bin,
                f"--host={host}",
                f"--port={port}",
                f"--user={user}",
                "--single-transaction",
                "--quick",
                "--skip-lock-tables",
                name,
            ]
            env = os.environ.copy()
            if password:
                env['MYSQL_PWD'] = password

            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
                with gzip.open(target_file, 'wb') as f_out:
                    shutil.copyfileobj(proc.stdout, f_out)
                proc.communicate()
                if proc.returncode == 0 and target_file.exists() and target_file.stat().st_size > 0:
                    return True, target_file
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"mysqldump execution failed: {e}. Falling back to dumpdata."))

        # Fallback to dumpdata if mysqldump not available or failed
        return self._backup_dumpdata(backup_dir, base_filename)

    def _backup_sqlite(self, db_conf, backup_dir, base_filename):
        target_file = backup_dir / f"{base_filename}.sqlite3.gz"
        db_path = Path(db_conf.get('NAME', ''))
        if db_path.exists() and db_path.is_file():
            try:
                with open(db_path, 'rb') as f_in, gzip.open(target_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
                return True, target_file
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"SQLite file backup failed: {e}"))
                return False, None
        return self._backup_dumpdata(backup_dir, base_filename)

    def _backup_dumpdata(self, backup_dir, base_filename):
        from django.core.management import call_command
        target_file = backup_dir / f"{base_filename}_data.json.gz"
        try:
            temp_json = backup_dir / f"tmp_{base_filename}.json"
            with open(temp_json, 'w', encoding='utf-8') as f:
                call_command('dumpdata', '--exclude', 'contenttypes', '--exclude', 'auth.permission', stdout=f)
            with open(temp_json, 'rb') as f_in, gzip.open(target_file, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
            if temp_json.exists():
                temp_json.unlink()
            return True, target_file
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Django dumpdata failed: {e}"))
            return False, None

    def _prune_old_backups(self, backup_dir, retention):
        backups = sorted(
            [f for f in backup_dir.glob('db_backup_*') if f.is_file()],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        if len(backups) > retention:
            to_delete = backups[retention:]
            for old_file in to_delete:
                try:
                    old_file.unlink()
                    self.stdout.write(f"   Pruned older backup: {old_file.name}")
                except Exception:
                    pass
