import datetime
import logging

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.views.decorators.http import require_POST

from apps.admin_panel.models.contact_submission import ContactSubmission
from apps.admin_panel.models.contact_reply import ContactReply
from apps.admin_panel.models.admin_auth import Admin
from apps.admin_panel.models.admin_activity_log import AdminActivityLog
from apps.admin_panel.views.dashboard import _get_admin_from_session
from django.shortcuts import redirect

logger = logging.getLogger(__name__)

VALID_STATUSES = {'pending', 'in_progress', 'replied', 'closed'}
VALID_PRIORITIES = {'low', 'normal', 'high', 'urgent'}


# ─── CONTACT INBOX ────────────────────────────────────────────────────────────

def contacts_index(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id: return redirect('admin_login')
    """List contact submissions with search + status filtering (mirrors AdminContactController::index)."""
    search        = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', 'all').strip()

    qs = ContactSubmission.objects.all()

    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(email__icontains=search) |
            Q(mobile__icontains=search) |
            Q(reference_id__icontains=search) |
            Q(subject__icontains=search)
        )

    if status_filter != 'all':
        qs = qs.filter(status=status_filter)

    qs = qs.order_by('-created_at')

    paginator   = Paginator(qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj    = paginator.get_page(page_number)

    stats = {
        'total':       ContactSubmission.objects.count(),
        'pending':     ContactSubmission.objects.filter(status='pending').count(),
        'in_progress': ContactSubmission.objects.filter(status='in_progress').count(),
        'replied':     ContactSubmission.objects.filter(status='replied').count(),
        'closed':      ContactSubmission.objects.filter(status='closed').count(),
    }

    # Admin directory for assignment dropdowns + showing assignee names.
    admins = list(Admin.objects.all().values('id', 'name', 'email'))
    admin_name_map = {a['id']: a['name'] for a in admins}

    # Annotate each row with its assignee name + reply count for the table.
    reply_counts = {}
    sub_ids = [s.id for s in page_obj]
    if sub_ids:
        from django.db.models import Count
        for row in (ContactReply.objects
                    .filter(submission_id__in=sub_ids, is_internal_note=False)
                    .values('submission_id')
                    .annotate(c=Count('id'))):
            reply_counts[row['submission_id']] = row['c']
    for s in page_obj:
        s.assignee_name = admin_name_map.get(s.assigned_admin_id, '')
        s.reply_count = reply_counts.get(s.id, 0)

    return render(request, 'admin/contacts.html', {
        'submissions':    page_obj,
        'stats':          stats,
        'search':         search,
        'status_filter':  status_filter,
        'admins':         admins,
        'admin_name_map': admin_name_map,
    })


def _fmt_dt(dt):
    try:
        return dt.strftime('%d %b %Y, %I:%M %p') if dt else ''
    except Exception:
        return ''


def contacts_show(request, submission_id):
    """Return full submission data as JSON for the detail modal (mirrors AdminContactController::show).

    Hardened so the existing "Read more" modal can never break: every optional
    piece (ticketing columns + replies thread) is read defensively, so even a
    deploy-before-migrate window or a legacy row returns the core message.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    try:
        sub = get_object_or_404(ContactSubmission, id=submission_id)
    except Exception:
        # get_object_or_404 raises Http404 (handled by Django); anything else → JSON.
        return JsonResponse({'success': False, 'message': 'Submission not found.'}, status=404)

    # Core fields that have always existed.
    data = {
        'id':           sub.id,
        'reference_id': getattr(sub, 'reference_id', '') or '',
        'name':         sub.name,
        'email':        sub.email,
        'mobile':       sub.mobile,
        'company':      sub.company or '',
        'subject':      sub.subject,
        'message':      sub.message,
        'status':       sub.status,
        'created_at':   _fmt_dt(getattr(sub, 'created_at', None)),
    }

    # Ticketing extras — never let these break the core modal.
    try:
        data['priority'] = getattr(sub, 'priority', 'normal') or 'normal'
        data['assigned_admin_id'] = getattr(sub, 'assigned_admin_id', None)
        assignee_name = ''
        if data['assigned_admin_id']:
            a = Admin.objects.filter(id=data['assigned_admin_id']).first()
            assignee_name = a.name if a else ''
        data['assignee_name'] = assignee_name
    except Exception:
        data.setdefault('priority', 'normal')
        data.setdefault('assigned_admin_id', None)
        data.setdefault('assignee_name', '')

    try:
        data['replies'] = [
            {
                'id':               r.id,
                'message':          r.message,
                'admin_name':       r.admin_name or '',
                'is_internal_note': r.is_internal_note,
                'emailed':          r.emailed,
                'created_at':       _fmt_dt(r.created_at),
            }
            for r in sub.replies.all()
        ]
    except Exception:
        # e.g. contact_replies table not migrated yet — degrade gracefully.
        data['replies'] = []

    return JsonResponse({'success': True, 'data': data})


@require_POST
def contacts_update_status(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id: return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)
    """AJAX status update (mirrors AdminContactController::updateStatus)."""
    sub_id = request.POST.get('id')
    status = request.POST.get('status')

    if not sub_id or status not in VALID_STATUSES:
        return JsonResponse({'success': False, 'message': 'Invalid data.'}, status=400)

    sub = get_object_or_404(ContactSubmission, id=sub_id)
    sub.status = status
    sub.save(update_fields=['status', 'updated_at'])

    return JsonResponse({'success': True})


@require_POST
def contacts_delete(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id: return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)
    """AJAX delete (mirrors AdminContactController::destroy)."""
    sub_id = request.POST.get('id')
    if not sub_id:
        return JsonResponse({'success': False, 'message': 'ID required.'}, status=400)

    sub = get_object_or_404(ContactSubmission, id=sub_id)
    sub.delete()

    return JsonResponse({'success': True, 'message': 'Submission deleted.'})


# ─── TICKETING ACTIONS (module #8) ────────────────────────────────────────────

def _current_admin(request):
    """Return the logged-in Admin instance (or None)."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return None
    return Admin.objects.filter(id=admin_id).first()


@require_POST
def contacts_assign(request):
    """Assign (or unassign) a ticket to an admin."""
    if not _get_admin_from_session(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    sub_id = request.POST.get('id')
    raw_admin = (request.POST.get('admin_id') or '').strip()
    if not sub_id:
        return JsonResponse({'success': False, 'message': 'Ticket id required.'}, status=400)

    sub = get_object_or_404(ContactSubmission, id=sub_id)

    if raw_admin == '':
        sub.assigned_admin_id = None
        assignee_name = ''
    else:
        try:
            target_id = int(raw_admin)
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'message': 'Invalid admin id.'}, status=400)
        target = Admin.objects.filter(id=target_id).first()
        if not target:
            return JsonResponse({'success': False, 'message': 'Admin not found.'}, status=404)
        sub.assigned_admin_id = target_id
        assignee_name = target.name

    sub.save(update_fields=['assigned_admin_id', 'updated_at'])
    AdminActivityLog.log(
        f'Assigned ticket {sub.reference_id or sub.id} to {assignee_name or "nobody"}',
        'ContactSubmission', sub.id, request=request,
    )
    return JsonResponse({'success': True, 'assignee_name': assignee_name})


@require_POST
def contacts_set_priority(request):
    """Change a ticket's priority."""
    if not _get_admin_from_session(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    sub_id = request.POST.get('id')
    priority = (request.POST.get('priority') or '').strip()
    if not sub_id or priority not in VALID_PRIORITIES:
        return JsonResponse({'success': False, 'message': 'Invalid data.'}, status=400)

    sub = get_object_or_404(ContactSubmission, id=sub_id)
    sub.priority = priority
    sub.save(update_fields=['priority', 'updated_at'])
    return JsonResponse({'success': True})


@require_POST
def contacts_reply(request):
    """Add a reply or internal note to a ticket. Optionally email the customer."""
    admin = _current_admin(request)
    if not admin:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    sub_id = request.POST.get('id')
    message = (request.POST.get('message') or '').strip()
    is_internal = request.POST.get('is_internal_note') in ('1', 'on', 'true', 'True')
    want_email = request.POST.get('send_email') in ('1', 'on', 'true', 'True')

    if not sub_id or not message:
        return JsonResponse({'success': False, 'message': 'Message is required.'}, status=400)

    sub = get_object_or_404(ContactSubmission, id=sub_id)

    emailed = False
    # Only customer-facing replies can be emailed (never internal notes).
    if want_email and not is_internal and sub.email:
        try:
            from apps.agents.services.brevo import email_service
            html = (
                f"<p>Hi {sub.name},</p>"
                f"<p>{message.replace(chr(10), '<br>')}</p>"
                f"<p>Regarding your query <b>{sub.reference_id or ('#' + str(sub.id))}</b>: "
                f"{sub.subject}</p>"
                f"<p>— PadosiAgent Support</p>"
            )
            emailed = bool(email_service.send_generic(
                sub.email, sub.name, f"Re: {sub.subject}", html
            ))
        except Exception as exc:
            # Never let an email failure break saving the reply.
            logger.error("Contact reply email failed for ticket %s: %s", sub.id, exc)
            emailed = False

    ContactReply.objects.create(
        submission=sub,
        admin_id=admin.id,
        admin_name=admin.name,
        message=message,
        is_internal_note=is_internal,
        emailed=emailed,
    )

    # A customer-facing reply moves an open ticket to 'replied'.
    update_fields = ['last_reply_at', 'updated_at']
    sub.last_reply_at = datetime.datetime.now()
    if not is_internal and sub.status not in ('closed',):
        sub.status = 'replied'
        update_fields.append('status')
    sub.save(update_fields=update_fields)

    AdminActivityLog.log(
        f'{"Internal note" if is_internal else "Replied"} on ticket {sub.reference_id or sub.id}'
        + (' (emailed)' if emailed else ''),
        'ContactSubmission', sub.id, request=request,
    )

    return JsonResponse({
        'success': True,
        'emailed': emailed,
        'reply': {
            'message': message,
            'admin_name': admin.name,
            'is_internal_note': is_internal,
            'emailed': emailed,
            'created_at': datetime.datetime.now().strftime('%d %b %Y, %I:%M %p'),
        },
    })
