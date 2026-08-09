import os
import subprocess
import datetime
import zipfile
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings

class Command(BaseCommand):
    help = 'Creates a database backup using mysqldump and compresses it'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-zip',
            action='store_true',
            help='Do not compress the SQL file',
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
            self.stderr.write("Database name or user not configured in settings.")
            return

        # Prepare backup directory
        # Project root -> storage/backups
        project_root = Path(settings.BASE_DIR).parent
        backup_dir = project_root / 'storage' / 'backups'
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
        ]
        
        if db_password:
            dump_cmd.append(f"--password={db_password}")
            
        dump_cmd.append(db_name)

        self.stdout.write(f"Starting database dump to {sql_filepath}...")
        
        try:
            with open(sql_filepath, 'w', encoding='utf-8') as f:
                process = subprocess.run(dump_cmd, stdout=f, stderr=subprocess.PIPE, text=True)
                
            if process.returncode != 0:
                self.stderr.write(f"mysqldump failed: {process.stderr}")
                # Remove empty or corrupt file
                if sql_filepath.exists():
                    sql_filepath.unlink()
                return

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

        except FileNotFoundError:
            self.stderr.write("mysqldump executable not found. Make sure it is in your system PATH or XAMPP is installed.")
        except Exception as e:
            self.stderr.write(f"An error occurred: {e}")
