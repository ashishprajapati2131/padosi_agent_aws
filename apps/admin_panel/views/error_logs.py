import json
from django.shortcuts import render, redirect, get_object_or_404
from django.db import models
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.admin_panel.models import ErrorLog
from apps.admin_panel.models.admin_activity_log import AdminActivityLog

def error_logs_index(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    query = ErrorLog.objects.all().order_by('-timestamp')

    # Filters
    level = request.GET.get('level', 'all').strip()
    if level != 'all' and level:
        query = query.filter(level=level)

    module = request.GET.get('module', '').strip()
    if module:
        query = query.filter(module__icontains=module)

    search = request.GET.get('search', '').strip()
    if search:
        query = query.filter(
            models.Q(message__icontains=search) |
            models.Q(exception_type__icontains=search) |
            models.Q(url__icontains=search) |
            models.Q(user_info__icontains=search)
        )

    # Time Filter
    time_filter = request.GET.get('time', 'all').strip()
    if time_filter == '24h':
        query = query.filter(timestamp__gte=timezone.now() - timedelta(days=1))
    elif time_filter == '7d':
        query = query.filter(timestamp__gte=timezone.now() - timedelta(days=7))
    elif time_filter == '30d':
        query = query.filter(timestamp__gte=timezone.now() - timedelta(days=30))

    # Paginate by 25
    paginator = Paginator(query, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Distinct modules for filter helper
    modules = ErrorLog.objects.values_list('module', flat=True).distinct().order_by('module')

    # Severity stats
    critical_count = ErrorLog.objects.filter(level='CRITICAL').count()
    error_count = ErrorLog.objects.filter(level='ERROR').count()
    warning_count = ErrorLog.objects.filter(level='WARNING').count()

    context = {
        'page_obj': page_obj,
        'search': search,
        'selected_level': level,
        'selected_module': module,
        'selected_time': time_filter,
        'modules': modules,
        'critical_count': critical_count,
        'error_count': error_count,
        'warning_count': warning_count,
        'total_count': paginator.count,
    }

    return render(request, 'admin/advanced/error_logs/index.html', context)

def error_logs_show(request, id):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    log = get_object_or_404(ErrorLog, id=id)
    return render(request, 'admin/advanced/error_logs/show.html', {'log': log})

def error_logs_delete(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'clear_all':
            ErrorLog.objects.all().delete()
            AdminActivityLog.log('Cleared all system error logs', 'ErrorLog', request=request)
            messages.success(request, 'All error logs have been cleared successfully.')
            return redirect('admin_error_logs_index')
            
        elif action == 'clear_old':
            # Older than 30 days
            cutoff = timezone.now() - timedelta(days=30)
            deleted_count, _ = ErrorLog.objects.filter(timestamp__lt=cutoff).delete()
            AdminActivityLog.log(f'Cleared error logs older than 30 days ({deleted_count} logs deleted)', 'ErrorLog', request=request)
            messages.success(request, f'Cleared {deleted_count} logs older than 30 days.')
            return redirect('admin_error_logs_index')
            
        else:
            log_ids = request.POST.getlist('log_ids[]')
            if log_ids:
                ErrorLog.objects.filter(id__in=log_ids).delete()
                messages.success(request, 'Selected error logs deleted successfully.')
                return JsonResponse({'success': True})
            return JsonResponse({'success': False, 'message': 'No logs selected'})

    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)
