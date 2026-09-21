from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.views.decorators.http import require_POST, require_GET

from apps.admin_panel.models.contact_submission import ContactSubmission
from apps.admin_panel.views.dashboard import _get_admin_from_session


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
            Q(subject__icontains=search) |
            Q(message__icontains=search) |
            Q(company__icontains=search)
        )

    if status_filter != 'all':
        qs = qs.filter(status=status_filter)

    qs = qs.order_by('-created_at')

    paginator   = Paginator(qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj    = paginator.get_page(page_number)

    stats = {
        'total':   ContactSubmission.objects.count(),
        'pending': ContactSubmission.objects.filter(status='pending').count(),
        'replied': ContactSubmission.objects.filter(status='replied').count(),
        'closed':  ContactSubmission.objects.filter(status='closed').count(),
    }

    return render(request, 'admin/contacts.html', {
        'submissions':   page_obj,
        'stats':         stats,
        'search':        search,
        'status_filter': status_filter,
    })


@require_GET
def contacts_show(request, submission_id):
    admin_id = _get_admin_from_session(request)
    if not admin_id: return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)
    """Return full submission data as JSON for the detail modal (mirrors AdminContactController::show)."""
    sub = get_object_or_404(ContactSubmission, id=submission_id)
    return JsonResponse({
        'success': True,
        'data': {
            'id':           sub.id,
            'reference_id': sub.reference_id,
            'name':         sub.name,
            'email':        sub.email,
            'mobile':       sub.mobile,
            'company':      sub.company or '',
            'subject':      sub.subject,
            'message':      sub.message,
            'status':       sub.status,
            'created_at':   sub.created_at.strftime('%d %b %Y, %I:%M %p'),
        }
    })


@require_POST
def contacts_update_status(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id: return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)
    """AJAX status update (mirrors AdminContactController::updateStatus)."""
    sub_id = request.POST.get('id')
    status = request.POST.get('status')

    VALID_STATUSES = {'pending', 'replied', 'closed'}
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


@require_POST
def contacts_bulk_action(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id: return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)
    """AJAX bulk delete or bulk status update."""
    action = request.POST.get('action')
    ids = request.POST.getlist('ids[]') or request.POST.getlist('ids')

    if not ids:
        return JsonResponse({'success': False, 'message': 'No submissions selected.'}, status=400)

    subs = ContactSubmission.objects.filter(id__in=ids)
    count = subs.count()

    if action == 'delete':
        subs.delete()
        return JsonResponse({'success': True, 'message': f'Successfully deleted {count} submission(s).'})
    elif action in ('pending', 'replied', 'closed'):
        subs.update(status=action)
        return JsonResponse({'success': True, 'message': f'Updated status for {count} submission(s) to {action}.'})
    else:
        return JsonResponse({'success': False, 'message': 'Invalid bulk action.'}, status=400)

