"""Admin list and export for quick-registration leads."""

from io import BytesIO
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from openpyxl import Workbook

from apps.admin_panel.models import RegistrationLead
from apps.admin_panel.services.spreadsheet_safety import safe_cell, safe_csv_writer
from apps.admin_panel.views.dashboard import _get_admin_from_session

PAGE_SIZE = 20
STATUSES = ('Started', 'Completed', 'Abandoned')
EXPORT_HEADERS = [
    'Name',
    'Phone',
    'Status',
    'Ref Code',
    'Source URL',
    'IP Address',
    'Created At',
]


def _filters(request):
    search = (request.GET.get('search') or '').strip()
    status = (request.GET.get('status') or 'all').strip()
    date_from_raw = (request.GET.get('date_from') or '').strip()
    date_to_raw = (request.GET.get('date_to') or '').strip()
    date_from = parse_date(date_from_raw) if date_from_raw else None
    date_to = parse_date(date_to_raw) if date_to_raw else None
    if status not in STATUSES:
        status = 'all'
    if date_from_raw and date_from is None:
        date_from_raw = ''
    if date_to_raw and date_to is None:
        date_to_raw = ''
    return {
        'search': search,
        'status': status,
        'date_from': date_from_raw if date_from else '',
        'date_to': date_to_raw if date_to else '',
        'parsed_from': date_from,
        'parsed_to': date_to,
    }


def _filtered_queryset(filters):
    qs = RegistrationLead.objects.all()
    if filters['search']:
        qs = qs.filter(
            Q(name__icontains=filters['search']) | Q(phone__icontains=filters['search'])
        )
    if filters['status'] in STATUSES:
        qs = qs.filter(status=filters['status'])
    if filters['parsed_from']:
        qs = qs.filter(created_at__date__gte=filters['parsed_from'])
    if filters['parsed_to']:
        qs = qs.filter(created_at__date__lte=filters['parsed_to'])
    return qs


def _filter_query(filters):
    params = {}
    if filters['search']:
        params['search'] = filters['search']
    if filters['status'] in STATUSES:
        params['status'] = filters['status']
    if filters['date_from']:
        params['date_from'] = filters['date_from']
    if filters['date_to']:
        params['date_to'] = filters['date_to']
    return urlencode(params)


def _format_created(value):
    if not value:
        return ''
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime('%d %b %Y %H:%M')


def _export_rows(qs):
    rows = []
    for lead in qs.iterator():
        rows.append([
            lead.name,
            lead.phone,
            lead.status,
            lead.ref_code,
            lead.source_url,
            lead.ip_address or '',
            _format_created(lead.created_at),
        ])
    return rows


def _require_admin(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return None
    return admin


def quick_registration_leads_list(request):
    if not _require_admin(request):
        return redirect('admin_login')

    filters = _filters(request)
    qs = _filtered_queryset(filters)
    paginator = Paginator(qs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    today = timezone.now().date()

    return render(request, 'admin/quick_registration_leads/list.html', {
        'leads': page_obj.object_list,
        'page_obj': page_obj,
        'search': filters['search'],
        'statusFilter': filters['status'],
        'dateFrom': filters['date_from'],
        'dateTo': filters['date_to'],
        'filter_query': _filter_query(filters),
        'total_rows': paginator.count,
        'stats': {
            'total': RegistrationLead.objects.count(),
            'today': RegistrationLead.objects.filter(created_at__date=today).count(),
            'started': RegistrationLead.objects.filter(status='Started').count(),
        },
    })


def quick_registration_leads_export_csv(request):
    if not _require_admin(request):
        return redirect('admin_login')

    filters = _filters(request)
    rows = _export_rows(_filtered_queryset(filters))
    filename = f"quick-registration-leads-{timezone.now().date().isoformat()}.csv"
    response = HttpResponse(content_type='text/csv; charset=UTF-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write(b'\xef\xbb\xbf')
    writer = safe_csv_writer(response)
    writer.writerow(EXPORT_HEADERS)
    writer.writerows(rows)
    return response


def quick_registration_leads_export_xlsx(request):
    if not _require_admin(request):
        return redirect('admin_login')

    filters = _filters(request)
    rows = _export_rows(_filtered_queryset(filters))
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Quick Registration Leads'
    sheet.append(EXPORT_HEADERS)
    for row in rows:
        sheet.append([safe_cell(value) for value in row])
    for column, width in zip('ABCDEFG', (28, 16, 14, 16, 42, 18, 20)):
        sheet.column_dimensions[column].width = width

    buffer = BytesIO()
    workbook.save(buffer)
    filename = f"quick-registration-leads-{timezone.now().date().isoformat()}.xlsx"
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
