import os
import subprocess
import datetime
import zipfile
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

BACKUP_TIMEOUT_SECONDS = 300


class Command(BaseCommand):
    help = 'Creates a database backup using mysqldump and compresses it'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-zip',
            action='store_true',
            help='Do not compress the SQL file',
        )
        parser.add_argument(
            '--retention',
            type=int,
            default=7,
            help='Number of most recent backups made by this command to keep. Default is 7.',
        )

    def handle(self, *args, **options):
        # Extract DB settings
        db_settings = settings.DATABASES['default']
        db_name = db_settings.get('NAME')
        db_user = db_settings.get('USER')
        db_password = db_settings.get('PASSWORD')
        db_host = db_settings.get('HOST', '127.0.0.1')
        db_port = db_settings.get('PORT', '3306')

        if not db_name or not db_user:
            raise CommandError("Database name or user not configured in settings.")

        # Prepare backup directory inside project backups folder
        backup_dir = Path(settings.BASE_DIR) / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        sql_filename = f"{db_name}_{timestamp}.sql"
        sql_filepath = backup_dir / sql_filename
        
        # Try to find mysqldump
        mysqldump_path = "mysqldump"
        xampp_mysqldump = r"C:\xampp\mysql\bin\mysqldump.exe"
        if os.path.exists(xampp_mysqldump):
            mysqldump_path = xampp_mysqldump
            
        dump_cmd = [
            mysqldump_path,
            f"--user={db_user}",
            f"--host={db_host}",
            f"--port={db_port}",
            db_name,
        ]
        # Password via env, not argv: argv is visible to every user in `ps`.
        env = os.environ.copy()
        if db_password:
            env['MYSQL_PWD'] = db_password

        self.stdout.write(f"Starting database dump to {sql_filepath}...")
        
        try:
            with open(sql_filepath, 'w', encoding='utf-8') as f:
                # Bounded: this also runs inside an admin web request (System > Backups).
                try:
                    process = subprocess.run(dump_cmd, stdout=f, stderr=subprocess.PIPE, text=True, env=env,
                                             timeout=BACKUP_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    process = None
            if process is None:
                if sql_filepath.exists():
                    sql_filepath.unlink()
                raise CommandError(f"mysqldump timed out after {BACKUP_TIMEOUT_SECONDS}s")
                
            if process.returncode != 0:
                # Remove empty or corrupt file
                if sql_filepath.exists():
                    sql_filepath.unlink()
                raise CommandError(f"mysqldump failed: {process.stderr}")

            self.stdout.write(self.style.SUCCESS('Database dump successful.'))
            
            if not options['no_zip']:
                zip_filename = f"{db_name}_{timestamp}.zip"
                zip_filepath = backup_dir / zip_filename
                
                self.stdout.write(f"Compressing to {zip_filepath}...")
                with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(sql_filepath, arcname=sql_filename)
                
                # Remove raw SQL file after successful zip
                sql_filepath.unlink()
                self.stdout.write(self.style.SUCCESS(f'Successfully created backup: {zip_filepath}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Successfully created backup: {sql_filepath}'))
            self._prune_old_backups(backup_dir, db_name, options['retention'])

        except CommandError:
            raise
        except FileNotFoundError as e:
            raise CommandError("mysqldump executable not found. Make sure it is in your system PATH or XAMPP is installed.") from e
        except Exception as e:
            raise CommandError(f"An error occurred: {e}") from e

    def _prune_old_backups(self, backup_dir, db_name, retention):
        # This command's files are {db_name}_YYYY-MM-DD-HH-MM-SS.(zip|sql); backup_database
        # prunes only its own db_backup_* files, so these were never removed.
        backups = sorted(
            [f for f in backup_dir.glob(f'{db_name}_[0-9][0-9][0-9][0-9]-*') if f.is_file() and f.suffix in ('.zip', '.sql')],
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        for old_file in backups[retention:]:
            try:
                old_file.unlink()
                self.stdout.write(f"Pruned older backup: {old_file.name}")
            except OSError:
                pass
