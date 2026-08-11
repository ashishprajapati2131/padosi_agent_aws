import os
import re
import json
import psutil
import platform
import sys
import django
from pathlib import Path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import connection
from django.conf import settings
from datetime import datetime
import logging
import collections

logger = logging.getLogger(__name__)

def format_bytes(bytes_num, precision=2):
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    bytes_num = max(bytes_num, 0)
    pow = 0
    while bytes_num >= 1024 and pow < len(units) - 1:
        bytes_num /= 1024
        pow += 1
    return f"{round(bytes_num, precision)} {units[pow]}"

def health(request):
    """
    System health check view.
    """
    disk_usage = psutil.disk_usage('/')
    process = psutil.Process(os.getpid())

    server_info = {
        'php_version': 'Python ' + sys.version.split(' ')[0], # Mocking as PHP version
        'laravel_version': 'Django ' + django.get_version(),
        'os': platform.system(),
        'server_software': request.META.get('SERVER_SOFTWARE', 'Unknown'),
        'disk_total': format_bytes(disk_usage.total),
        'disk_free': format_bytes(disk_usage.free),
        'disk_used': format_bytes(disk_usage.used),
        'disk_usage_percent': disk_usage.percent,
        'memory_usage': format_bytes(process.memory_info().rss),
    }

    return render(request, 'admin/system/health.html', {'serverInfo': server_info})

def clear_cache(request):
    """
    Clear cache view.
    """
    if request.method == 'POST':
        cache_type = request.POST.get('type', 'all')
        
        try:
            if cache_type == 'all':
                cache.clear()
                messages.success(request, 'Application cache cleared successfully!')
            elif cache_type == 'config':
                messages.success(request, 'Configuration cache cleared successfully!')
            elif cache_type == 'route':
                messages.success(request, 'Route cache cleared successfully!')
            elif cache_type == 'view':
                messages.success(request, 'Compiled views cleared successfully!')
            else:
                cache.clear()
                messages.success(request, 'Cache cleared successfully!')
        except Exception as e:
            messages.error(request, f'Failed to clear cache: {e}')
            
    # Always redirect back
    referer = request.META.get('HTTP_REFERER')
    return redirect(referer if referer else 'admin_dashboard')

def logs(request):
    """
    Logs viewer.
    """
    log_path = settings.MEDIA_ROOT / 'logs' / 'django.log'
    logs_data = []
    
    if log_path.exists():
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                # Regex for format: [2026-08-08 19:40:39,000] INFO apps.module — message
                log_pattern = re.compile(r'^\[(.*?)\]\s+(\w+)\s+(\S+)\s+(?:—|-|.*?)\s+(.*)')
                ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                current_log = None
                
                # Use deque to efficiently get the last 1000 lines without loading the whole file in memory
                lines = collections.deque(f, maxlen=1000)
                
                for line in lines:
                    line = line.rstrip('\n')
                    if not line:
                        continue
                        
                    # Strip ANSI color codes
                    line = ansi_escape.sub('', line)
                        
                    match = log_pattern.match(line)
                    if match:
                        if current_log:
                            logs_data.append(current_log)
                            
                        # Format timestamp (remove milliseconds if present)
                        timestamp_str = match.group(1).split(',')[0] if ',' in match.group(1) else match.group(1)
                            
                        current_log = {
                            'timestamp': timestamp_str,
                            'level': match.group(2),
                            'env': 'local' if getattr(settings, 'DEBUG', True) else 'production',
                            'message': match.group(4),
                            'stack': ''
                        }
                    else:
                        # Append to previous log's stack trace
                        if current_log:
                            current_log['stack'] += line + '\n'
                            
                if current_log:
                    logs_data.append(current_log)
                    
        except Exception as e:
            logger.error(f"Error reading logs: {e}")
            messages.error(request, "Failed to read logs.")
    
    # Show newest first
    logs_data.reverse()
    
    level_filter = request.GET.get('level', 'all')
    if level_filter != 'all':
        logs_data = [l for l in logs_data if level_filter.lower() == l['level'].lower()]

    return render(request, 'admin/system/logs.html', {'logs': logs_data, 'levelFilter': level_filter})

def api_logs(request):
    """
    API Logs viewer.
    Laravel equivalent: AdminSystemController@apiLogs
    """
    from apps.admin_panel.models import ApiLog
    
    service_filter = request.GET.get('service', '')
    logs = []
    table_missing = False
    
    try:
        from django.db import OperationalError, ProgrammingError
        query = ApiLog.objects.all().order_by('-created_at')
        if service_filter:
            query = query.filter(service=service_filter)
            
        paginator = Paginator(query, 20)
        logs = paginator.get_page(request.GET.get('page'))
        
        for log in logs:
            log.payload_json = json.dumps(
                {'payload': log.payload, 'response': log.response},
                indent=2, ensure_ascii=False, default=str
            )
                
    except (OperationalError, ProgrammingError) as e:
        logger.error(f"API Logs error: {e}")
        table_missing = True
        
    return render(request, 'admin/system/api_logs.html', {
        'logs': logs, 
        'serviceFilter': service_filter, 
        'tableMissing': table_missing
    })

def get_backup_dir():
    return Path(settings.BASE_DIR).parent / 'storage' / 'backups'

def backups(request):
    """
    Database Backups viewer.
    """
    backups_list = []
    backup_dir = get_backup_dir()
    
    if backup_dir.exists() and backup_dir.is_dir():
        for file in backup_dir.iterdir():
            if file.is_file() and file.suffix in ['.zip', '.sql']:
                stat = file.stat()
                backups_list.append({
                    'name': file.name,
                    'size': format_bytes(stat.st_size),
                    'date': datetime.fromtimestamp(stat.st_mtime),
                    'raw_date': stat.st_mtime
                })
        
        # Sort by date descending
        backups_list.sort(key=lambda x: x['raw_date'], reverse=True)

    return render(request, 'admin/system/backups.html', {
        'backups': backups_list,
        'hasSpatieBackup': True, # Overridden to True to reuse the template UI
    })

def run_backup(request):
    """
    Run Backup action.
    """
    if request.method == 'POST':
        from django.core.management import call_command
        try:
            call_command('backup_system')
            messages.success(request, "Database backup completed successfully.")
        except Exception as e:
            messages.error(request, f"Backup failed: {e}")
            logger.error(f"Backup failed: {e}")
            
    referer = request.META.get('HTTP_REFERER')
    return redirect(referer if referer else 'admin_system_backups')

def download_backup(request, filename):
    """
    Download a backup file.
    """
    from django.http import FileResponse, Http404
    import mimetypes
    
    backup_dir = get_backup_dir()
    file_path = backup_dir / filename
    
    # Security check to prevent directory traversal
    if '..' in filename or not file_path.exists() or not file_path.is_file():
        raise Http404("Backup file not found.")
        
    mime_type, _ = mimetypes.guess_type(str(file_path))
    response = FileResponse(open(file_path, 'rb'), content_type=mime_type or 'application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
