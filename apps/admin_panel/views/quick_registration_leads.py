"""Admin list and export for quick-registration leads."""

import datetime
from io import BytesIO
import logging
from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from openpyxl import Workbook

from apps.admin_panel.models import RegistrationLead
from apps.admin_panel.services.spreadsheet_safety import safe_cell, safe_csv_writer
from apps.admin_panel.views.dashboard import _get_admin_from_session

logger = logging.getLogger(__name__)

PAGE_SIZE = 20
ABANDON_AFTER_DAYS = 30
STATUSES = (
    RegistrationLead.STATUS_QUICK_REGISTERED,
    RegistrationLead.STATUS_FORM_STARTED,
    RegistrationLead.STATUS_FORM_COMPLETED,
    RegistrationLead.STATUS_PAYMENT_COMPLETED,
    RegistrationLead.STATUS_CONVERTED,
    RegistrationLead.STATUS_ABANDONED,
)
FORM_FILTERS = ('filled', 'not_filled')
PAYMENT_FILTERS = (
    RegistrationLead.PAYMENT_NONE,
    RegistrationLead.PAYMENT_PENDING,
    RegistrationLead.PAYMENT_COMPLETED,
    RegistrationLead.PAYMENT_FAILED,
)
EXPORT_HEADERS = [
    'Name',
    'Phone',
    'Registered At',
    'Status',
    'Form Status',
    'Payment Status',
    'Ref Code',
    'Source URL',
]


def _filters(request):
    search = (request.GET.get('search') or '').strip()
    status = (request.GET.get('status') or 'open').strip()
    form_filled = (request.GET.get('form') or 'all').strip()
    payment = (request.GET.get('payment') or 'all').strip()
    date_from_raw = (request.GET.get('date_from') or '').strip()
    date_to_raw = (request.GET.get('date_to') or '').strip()
    date_from = parse_date(date_from_raw) if date_from_raw else None
    date_to = parse_date(date_to_raw) if date_to_raw else None
    if status not in STATUSES and status not in ('all', 'open'):
        status = 'open'
    if form_filled not in FORM_FILTERS:
        form_filled = 'all'
    if payment not in PAYMENT_FILTERS:
        payment = 'all'
    if date_from_raw and date_from is None:
        date_from_raw = ''
    if date_to_raw and date_to is None:
        date_to_raw = ''
    return {
        'search': search,
        'status': status,
        'form': form_filled,
        'payment': payment,
        'date_from': date_from_raw if date_from else '',
        'date_to': date_to_raw if date_to else '',
        'parsed_from': date_from,
        'parsed_to': date_to,
    }


def _sync_active_agent_conversions():
    """Ensure any leads with matching active agents are marked converted and removed from open list."""
    try:
        from apps.agents.models import Agent
        active_phones = set(
            Agent.objects.filter(status='active').exclude(mobile='').values_list('mobile', flat=True)
        )
        if active_phones:
            clean_phones = {p[-10:] for p in active_phones if len(p) >= 10}
            RegistrationLead.objects.filter(
                phone__in=clean_phones,
            ).exclude(status=RegistrationLead.STATUS_CONVERTED).update(
                status=RegistrationLead.STATUS_CONVERTED,
                converted_at=timezone.now(),
                form_filled=True,
                payment_status=RegistrationLead.PAYMENT_COMPLETED,
            )
    except Exception as e:
        logger.warning(f"Error syncing active agent conversions: {e}")


def _filtered_queryset(filters):
    _sync_active_agent_conversions()
    qs = RegistrationLead.objects.all()
    status = filters['status']
    if status == 'open':
        qs = qs.exclude(status=RegistrationLead.STATUS_CONVERTED)
    elif status in STATUSES:
        qs = qs.filter(status=status)
    if filters['search']:
        qs = qs.filter(
            Q(name__icontains=filters['search']) | Q(phone__icontains=filters['search'])
        )
    if filters['form'] == 'filled':
        qs = qs.filter(form_filled=True)
    elif filters['form'] == 'not_filled':
        qs = qs.filter(form_filled=False)
    if filters['payment'] in PAYMENT_FILTERS:
        qs = qs.filter(payment_status=filters['payment'])
    if filters['parsed_from']:
        start_dt = datetime.datetime.combine(filters['parsed_from'], datetime.time.min)
        qs = qs.filter(created_at__gte=start_dt)
    if filters['parsed_to']:
        end_dt = datetime.datetime.combine(filters['parsed_to'], datetime.time.max)
        qs = qs.filter(created_at__lte=end_dt)
    return qs


def _filter_query(filters):
    params = {}
    if filters['search']:
        params['search'] = filters['search']
    if filters['status'] and filters['status'] != 'open':
        params['status'] = filters['status']
    if filters['form'] != 'all':
        params['form'] = filters['form']
    if filters['payment'] != 'all':
        params['payment'] = filters['payment']
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
    labels = dict(RegistrationLead.STATUS_CHOICES)
    pay_labels = dict(RegistrationLead.PAYMENT_CHOICES)
    for lead in qs.iterator():
        rows.append([
            lead.name,
            lead.phone,
            _format_created(lead.created_at),
            labels.get(lead.status, lead.status),
            'Filled' if lead.form_filled else 'Not filled',
            pay_labels.get(lead.payment_status, lead.payment_status),
            lead.ref_code,
            lead.source_url,
        ])
    return rows


def _require_admin(request):
    return _get_admin_from_session(request)


def _abandon_stale_leads():
    """Quiet leads that never finished the form are marked abandoned after 30 days."""
    cutoff = timezone.now() - timezone.timedelta(days=ABANDON_AFTER_DAYS)
    RegistrationLead.objects.filter(
        status__in=(
            RegistrationLead.STATUS_QUICK_REGISTERED,
            RegistrationLead.STATUS_FORM_STARTED,
        ),
        updated_at__lt=cutoff,
    ).update(status=RegistrationLead.STATUS_ABANDONED)


def quick_registration_leads_list(request):
    if not _require_admin(request):
        return redirect('admin_login')

    _abandon_stale_leads()
    filters = _filters(request)
    qs = _filtered_queryset(filters)
    paginator = Paginator(qs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    today_start = datetime.datetime.combine(timezone.now().date(), datetime.time.min)
    open_qs = RegistrationLead.objects.exclude(status=RegistrationLead.STATUS_CONVERTED)

    return render(request, 'admin/quick_registration_leads/list.html', {
        'leads': page_obj.object_list,
        'page_obj': page_obj,
        'search': filters['search'],
        'statusFilter': filters['status'],
        'formFilter': filters['form'],
        'paymentFilter': filters['payment'],
        'dateFrom': filters['date_from'],
        'dateTo': filters['date_to'],
        'filter_query': _filter_query(filters),
        'total_rows': paginator.count,
        'status_choices': RegistrationLead.STATUS_CHOICES,
        'stats': {
            'total': open_qs.count(),
            'today': open_qs.filter(created_at__gte=today_start).count(),
            'started': open_qs.filter(status=RegistrationLead.STATUS_QUICK_REGISTERED).count(),
            'form_started': open_qs.filter(status=RegistrationLead.STATUS_FORM_STARTED).count(),
            'form_completed': open_qs.filter(status=RegistrationLead.STATUS_FORM_COMPLETED).count(),
            'converted': RegistrationLead.objects.filter(status=RegistrationLead.STATUS_CONVERTED).count(),
        },
    })


@require_POST
def quick_registration_lead_delete(request, lead_id):
    if not _require_admin(request):
        return redirect('admin_login')

    lead = get_object_or_404(RegistrationLead, pk=lead_id)
    name = lead.name
    phone = lead.phone
    lead.delete()
    messages.success(request, f'Lead {name} ({phone}) deleted successfully.')
    return redirect('admin_quick_registration_leads')


def quick_registration_leads_export_csv(request):
    if not _require_admin(request):
        return redirect('admin_login')

    _abandon_stale_leads()
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

    _abandon_stale_leads()
    filters = _filters(request)
    rows = _export_rows(_filtered_queryset(filters))
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Quick Registration Leads'
    sheet.append(EXPORT_HEADERS)
    for row in rows:
        sheet.append([safe_cell(value) for value in row])
    for column, width in zip('ABCDEFGH', (28, 16, 20, 20, 14, 16, 16, 42)):
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
