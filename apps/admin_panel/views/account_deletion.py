import json
import logging
from datetime import datetime

from django.db import connection, transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator

from apps.agents.models import (
    AccountDeletionRequest,
    Agent,
    AgentProfile,
    Invoice,
    AgentSubscription,
)
from apps.admin_panel.models import AdminActivityLog
from .dashboard import _get_admin_from_session

logger = logging.getLogger(__name__)


def deletion_requests_list(request):
    """
    Renders the admin dashboard list of all account deletion requests.
    Supports filtering by status (PENDING, COMPLETED, REJECTED).
    All agent profile data is preserved so admin can review and terminate / reactivate.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login_page')

    status_filter = request.GET.get('status', '').strip().upper()
    search_query = request.GET.get('q', '').strip()

    qs = AccountDeletionRequest.objects.all().order_by('-created_at')

    if status_filter in ['PENDING', 'COMPLETED', 'REJECTED']:
        qs = qs.filter(status=status_filter)

    if search_query:
        from django.db.models import Q
        qs = qs.filter(
            Q(reference_id__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(mobile__icontains=search_query) |
            Q(identifier__icontains=search_query)
        )

    # Statistics
    stats = {
        'total': AccountDeletionRequest.objects.count(),
        'pending': AccountDeletionRequest.objects.filter(status='PENDING').count(),
        'completed': AccountDeletionRequest.objects.filter(status='COMPLETED').count(),
        'rejected': AccountDeletionRequest.objects.filter(status='REJECTED').count(),
    }

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Pre-serialize json data for bug-proof details modal
    for req in page_obj.object_list:
        try:
            req.json_data = json.dumps(req.to_dict())
        except Exception:
            req.json_data = json.dumps({
                'id': req.id,
                'reference_id': req.reference_id,
                'fullname': req.identifier,
                'email': req.email,
                'mobile': req.mobile,
                'pan_number': req.identifier,
                'reason_category': req.reason,
                'reason_details': req.reason,
                'status': req.status,
                'is_verified': req.is_verified,
                'rejection_reason': req.rejection_reason or '',
                'admin_notes': req.admin_notes or '',
                'created_at': req.created_at.strftime('%d %b %Y, %I:%M %p') if req.created_at else '',
                'processed_at': req.processed_at.strftime('%d %b %Y, %I:%M %p') if req.processed_at else '',
            })

    return render(request, 'admin/deletion_requests/list.html', {
        'page_obj': page_obj,
        'requests': page_obj.object_list,
        'stats': stats,
        'status_filter': status_filter,
        'search_query': search_query,
    })


@require_POST
def terminate_agent_account(request):
    """
    Admin-only execution to terminate an account based on a deletion request.
    Preserves all data in the database while:
      - Updating Agent.status='deleted'
      - Suspending login (User.status='suspended', AuthUser.is_active=False)
      - Hiding public profile and review cards
      - Marking AccountDeletionRequest.status='COMPLETED'
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            request_id = data.get('request_id')
            admin_notes = data.get('admin_notes', '').strip()
        else:
            request_id = request.POST.get('request_id')
            admin_notes = request.POST.get('admin_notes', '').strip()

        request_id = int(request_id)
    except Exception:
        return JsonResponse({'success': False, 'message': 'Invalid input parameters'}, status=400)

    try:
        del_req = AccountDeletionRequest.objects.get(pk=request_id)
    except AccountDeletionRequest.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Account deletion request not found'}, status=404)

    # Resolve Agent
    agent = del_req.agent
    if not agent:
        agent = Agent.objects.filter(email__iexact=del_req.email).first()
        if not agent and del_req.mobile:
            agent = Agent.objects.filter(mobile=del_req.mobile).first()

    now = datetime.now()

    with transaction.atomic():
        if agent:
            # Hide public profile and card while keeping all records intact
            try:
                profile = getattr(agent, 'profile', None)
                if profile:
                    profile.is_profile_visible = False
                    profile.is_card_visible = False
                    profile.save(update_fields=['is_profile_visible', 'is_card_visible'])
            except Exception as e:
                logger.warning(f"Error updating visibility for agent {agent.id}: {e}")

            # Mark agent status as deleted
            agent.status = 'deleted'
            agent.save(update_fields=['status'])

            # Suspend user accounts to block login
            if agent.email:
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE users SET status = 'suspended' WHERE LOWER(email) = LOWER(%s)", [agent.email])

            if agent.user:
                agent.user.is_active = False
                agent.user.save(update_fields=['is_active'])

        # Finalize the deletion request record
        del_req.status = 'COMPLETED'
        del_req.processed_at = now
        del_req.processed_by_admin_name = f"Admin #{admin_id}"
        del_req.admin_notes = f"{del_req.admin_notes}\n[Admin Termination]: {admin_notes}".strip()
        del_req.save()

        # Log admin audit activity
        AdminActivityLog.log(
            'Account Terminated',
            'agent',
            agent.id if agent else None,
            details=(
                f"Account terminated for {del_req.email} (Ref: {del_req.reference_id}). "
                f"Login suspended, public profile hidden. All records kept."
            ),
            request=request
        )

    return JsonResponse({
        'success': True,
        'message': f"Account for {del_req.email} has been successfully terminated.",
    })


@require_POST
def activate_agent_account(request):
    """
    Admin-only execution to reactivate a terminated account.
    Restores Agent.status='active', User.status='active', and re-enables public profile.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            request_id = data.get('request_id')
            admin_notes = data.get('admin_notes', '').strip()
        else:
            request_id = request.POST.get('request_id')
            admin_notes = request.POST.get('admin_notes', '').strip()

        request_id = int(request_id)
    except Exception:
        return JsonResponse({'success': False, 'message': 'Invalid input parameters'}, status=400)

    try:
        del_req = AccountDeletionRequest.objects.get(pk=request_id)
    except AccountDeletionRequest.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Account deletion request not found'}, status=404)

    # Resolve Agent
    agent = del_req.agent
    if not agent:
        agent = Agent.objects.filter(email__iexact=del_req.email).first()
        if not agent and del_req.mobile:
            agent = Agent.objects.filter(mobile=del_req.mobile).first()

    now = datetime.now()

    with transaction.atomic():
        if agent:
            # Restore public profile and card
            try:
                profile = getattr(agent, 'profile', None)
                if profile:
                    profile.is_profile_visible = True
                    profile.is_card_visible = True
                    profile.save(update_fields=['is_profile_visible', 'is_card_visible'])
            except Exception as e:
                logger.warning(f"Error restoring visibility for agent {agent.id}: {e}")

            # Mark agent status as active
            agent.status = 'active'
            agent.save(update_fields=['status'])

            # Reactivate user account
            if agent.email:
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE users SET status = 'active' WHERE LOWER(email) = LOWER(%s)", [agent.email])

            if agent.user:
                agent.user.is_active = True
                agent.user.save(update_fields=['is_active'])

        # Reset deletion request status to PENDING or mark as reactivated
        del_req.status = 'PENDING'
        del_req.processed_at = now
        del_req.processed_by_admin_name = f"Admin #{admin_id}"
        del_req.admin_notes = f"{del_req.admin_notes}\n[Admin Reactivated]: {admin_notes}".strip()
        del_req.save()

        # Log admin audit activity
        AdminActivityLog.log(
            'Account Reactivated',
            'agent',
            agent.id if agent else None,
            details=f"Account reactivated for {del_req.email} (Ref: {del_req.reference_id}) by admin.",
            request=request
        )

    return JsonResponse({
        'success': True,
        'message': f"Account for {del_req.email} has been successfully reactivated and restored.",
    })


@require_POST
def reject_deletion_request(request):
    """
    Admin rejection of an account deletion request due to data mismatch, pending policies, or disputes.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            request_id = data.get('request_id')
            rejection_reason = data.get('rejection_reason', '').strip()
        else:
            request_id = request.POST.get('request_id')
            rejection_reason = request.POST.get('rejection_reason', '').strip()

        request_id = int(request_id)
    except Exception:
        return JsonResponse({'success': False, 'message': 'Invalid input parameters'}, status=400)

    try:
        del_req = AccountDeletionRequest.objects.get(pk=request_id)
    except AccountDeletionRequest.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Request not found'}, status=404)

    if not rejection_reason:
        rejection_reason = "Data mismatch in account credentials"

    del_req.status = 'REJECTED'
    del_req.rejection_reason = rejection_reason
    del_req.processed_at = datetime.now()
    del_req.processed_by_admin_name = f"Admin #{admin_id}"
    del_req.save()

    AdminActivityLog.log(
        'Account Deletion Rejected',
        'account_deletion_request',
        del_req.id,
        details=f"Rejected request {del_req.reference_id}: {rejection_reason}",
        request=request
    )

    return JsonResponse({
        'success': True,
        'message': f"Request {del_req.reference_id} marked as rejected. Reason: {rejection_reason}",
    })
