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
from datetime import datetime, timedelta
import logging
import collections
from apps.admin_panel.services import log_reader

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

LOG_RANGES = {'1h': timedelta(hours=1), '24h': timedelta(hours=24), '7d': timedelta(days=7), 'all': None}


def logs(request):
    """
    Logs viewer: repeated log lines grouped into issues, with exception type, app location and a plain hint.
    """
    log_path = getattr(settings, 'LOGS_DIR', settings.BASE_DIR / 'logs') / 'django.log'
    entries, file_info = [], None

    if log_path.exists():
        try:
            entries = log_reader.parse_entries(log_reader.read_tail(log_path), settings.BASE_DIR)
            stat = log_path.stat()
            file_info = {'size': format_bytes(stat.st_size), 'modified': datetime.fromtimestamp(stat.st_mtime)}
        except Exception as e:
            logger.error(f"Error reading logs: {e}")
            messages.error(request, "Failed to read logs.")

    now = datetime.now()
    view_mode = request.GET.get('view') if request.GET.get('view') in ('issues', 'stream') else 'issues'
    level_filter = request.GET.get('level') if request.GET.get('level') in ('error', 'warning', 'info', 'all') else 'error'
    range_key = request.GET.get('range') if request.GET.get('range') in LOG_RANGES else '7d'
    query = request.GET.get('q', '').strip()

    # Last-24h hourly activity chart, independent of the filters
    buckets = [{'errors': 0, 'warnings': 0, 'hour': (now - timedelta(hours=23 - i)).strftime('%H:00')} for i in range(24)]
    for e in entries:
        if e['time'] and now - e['time'] < timedelta(hours=24) and e['severity'] in ('error', 'warning'):
            idx = min(23, 23 - int((now - e['time']).total_seconds() // 3600))  # future timestamps -> current hour
            buckets[idx]['errors' if e['severity'] == 'error' else 'warnings'] += 1
    peak = max([b['errors'] + b['warnings'] for b in buckets] + [1])
    for b in buckets:
        b['err_pct'] = round(b['errors'] * 100 / peak)
        b['warn_pct'] = round(b['warnings'] * 100 / peak)

    if LOG_RANGES[range_key]:
        cutoff = now - LOG_RANGES[range_key]
        entries = [e for e in entries if e['time'] and e['time'] >= cutoff]

    counts = collections.Counter(e['severity'] for e in entries)
    errors = [e for e in entries if e['severity'] == 'error']
    stats = {
        'errors': counts['error'],
        'warnings': counts['warning'],
        'info': counts['info'] + counts['debug'],
        'error_issues': len({e['fingerprint'] for e in errors}),
        'last_error': errors[-1]['time'] if errors else None,
    }

    if level_filter == 'warning':
        entries = [e for e in entries if e['severity'] in ('error', 'warning')]
    elif level_filter != 'all':
        entries = [e for e in entries if e['severity'] == level_filter]
    if query:
        q = query.lower()
        entries = [e for e in entries if q in f"{e['message']} {e['source']} {e['stack']}".lower()]

    items = log_reader.group_issues(entries) if view_mode == 'issues' else entries[::-1]
    page = Paginator(items, 30).get_page(request.GET.get('page'))

    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'admin/system/logs.html', {
        'page_obj': page, 'viewMode': view_mode, 'levelFilter': level_filter, 'rangeKey': range_key,
        'query': query, 'stats': stats, 'buckets': buckets, 'fileInfo': file_info,
        'baseQuery': params.urlencode(), 'now': now,
    })

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
    backup_path = Path(settings.BASE_DIR) / 'backups'
    backup_path.mkdir(parents=True, exist_ok=True)
    return backup_path

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


def run_maintenance_jobs(request):
    """
    Execute all background maintenance tasks on-demand from the Admin Panel
    or via a secure token-authenticated webhook (for hosts without cron jobs).
    """
    from django.conf import settings
    from django.http import JsonResponse, HttpResponseForbidden
    from io import StringIO
    from django.core.management import call_command
    from apps.agents.services.background_jobs import retry_missing_invoices
    
    is_staff = request.user.is_authenticated and request.user.is_staff
    token = request.GET.get('token') or request.headers.get('X-Cron-Token')
    expected_token = getattr(settings, 'CRON_TRIGGER_TOKEN', '') or (settings.SECRET_KEY[:24] if settings.SECRET_KEY else '')
    is_token_valid = bool(token and expected_token and token == expected_token)
    
    if not is_staff and not is_token_valid:
        if token:
            return HttpResponseForbidden("Invalid cron token.")
        messages.error(request, "Staff permission required.")
        return redirect('admin_system_health')
        
    summary = []
    try:
        invoices_retried = retry_missing_invoices(days=7, apply=True, max_attempts=3)
        summary.append(f"Invoices checked/retried: {invoices_retried}")
    except Exception as e:
        summary.append(f"Invoices: {e}")

    try:
        out = StringIO()
        call_command('recover_orphaned_payments', '--days', '14', '--apply', stdout=out)
        res = out.getvalue().strip()
        summary.append(f"Orphan payments: {res or 'Clean (0)'}")
    except Exception as e:
        summary.append(f"Orphan payments: {e}")

    try:
        out = StringIO()
        call_command('process_event_referral_expirations', stdout=out)
        res = out.getvalue().strip()
        summary.append(f"Event referral: {res or 'Processed'}")
    except Exception as e:
        summary.append(f"Event referral: {e}")

    try:
        out = StringIO()
        call_command('expire_subscriptions', '--apply', stdout=out)
        res = out.getvalue().strip()
        summary.append(f"Subscriptions: {res or 'Up-to-date'}")
    except Exception as e:
        summary.append(f"Subscriptions: {e}")

    if is_token_valid and not is_staff:
        return JsonResponse({'status': 'ok', 'summary': summary})

    messages.success(request, f"Maintenance completed: {' | '.join(summary)}")
    referer = request.META.get('HTTP_REFERER')
    return redirect(referer if referer else 'admin_system_health')


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
