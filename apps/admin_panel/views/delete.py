import logging
import json
from django.db import connection
from django.http import JsonResponse
from .dashboard import _get_admin_from_session

logger = logging.getLogger(__name__)

def _log_delete(request, model, record_id, outcome, snapshot=None, severity="CRITICAL"):
    from apps.admin_panel.models import AdminActivityLog
    try:
        model_id = int(record_id)
    except (TypeError, ValueError):
        model_id = None
    details = {
        'outcome': outcome,
        'snapshot': snapshot or {},
    }
    AdminActivityLog.log(
        f'Admin delete: {model}',
        model_type=model,
        model_id=model_id,
        details=details,
        request=request,
        severity=severity,
        snapshot=snapshot,
    )


def admin_delete(request):
    """
    Phase 6B.5: Generic admin delete handler
    Replaces delete_agent() and supports multiple models matching Laravel's AdminDeleteController.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=400)

    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            record_id = data.get('id')
            model = data.get('model')
        else:
            record_id = request.POST.get('id')
            model = request.POST.get('model')
    except Exception:
        return JsonResponse({'success': False, 'message': 'Invalid data format'}, status=400)

    if not model or not record_id:
        return JsonResponse({'success': False, 'message': 'Missing model or id'}, status=400)

    snapshot = {}
    try:
        with connection.cursor() as cursor:
            if model == 'agent':
                # 1. Fetch complete agent snapshot before deletion
                cursor.execute("""
                    SELECT id, user_id, email, fullname, mobile, status, plan_type, agent_pincode, profession
                    FROM agents WHERE id = %s
                """, [record_id])
                agent_row = cursor.fetchone()
                if not agent_row:
                    return JsonResponse({'success': False, 'message': 'Record not found'}, status=404)
                
                agent_email = agent_row[2]
                cols_agent = ['id', 'user_id', 'email', 'fullname', 'mobile', 'status', 'plan_type', 'agent_pincode', 'profession']
                snapshot = dict(zip(cols_agent, [str(v) if v is not None else '' for v in agent_row]))

                # An agent with payment history is kept (status 'deleted'):
                # hard-deleting it with FK checks off orphaned its subscriptions
                # and invoices (needed for GST / refunds).
                from apps.agents.models import AgentSubscription, Invoice
                has_payments = (
                    AgentSubscription.objects.filter(agent_id=record_id, payment_status__in=['completed', 'refunded']).exists()
                    or Invoice.objects.filter(agent_id=record_id).exists()
                )
                if has_payments:
                    from apps.agents.models import Agent
                    Agent.objects.filter(pk=record_id).update(status='deleted')
                    if agent_email:
                        cursor.execute("UPDATE users SET status = 'suspended' WHERE LOWER(email) = LOWER(%s)", [agent_email])
                    _log_delete(request, model, record_id, 'soft-deleted (payment records kept)', snapshot=snapshot)
                    return JsonResponse({
                        'success': True,
                        'message': 'This agent has payment records, so the agent was marked deleted and the records were kept.',
                    })
                
                # 2. Backup agent record into agent_backup table
                try:
                    cursor.execute("""
                        INSERT INTO agent_backup (
                            id, user_id, event_id, distributor_id, fullname, email, google_id,
                            email_verified_at, mobile, registration_step, agent_pincode, latitude, longitude,
                            plan_type, trial_ends_at, upgrade_discount_percent, referred_by_code,
                            referral_reward_type, referral_reward_claimed, status, is_approved, approved_at,
                            badge, admin_notes, registration_draft, user_types, insurance_companies,
                            experience_range, client_base, achievement_photo_limit, profession, created_at, updated_at
                        )
                        SELECT
                            id, user_id, event_id, distributor_id, fullname, email, google_id,
                            email_verified_at, mobile, registration_step, agent_pincode, latitude, longitude,
                            plan_type, trial_ends_at, upgrade_discount_percent, referred_by_code,
                            referral_reward_type, referral_reward_claimed, status, is_approved, approved_at,
                            badge, admin_notes, registration_draft, user_types, insurance_companies,
                            experience_range, client_base, achievement_photo_limit, profession, created_at, updated_at
                        FROM agents WHERE id = %s
                        ON DUPLICATE KEY UPDATE
                            fullname = VALUES(fullname),
                            email = VALUES(email),
                            status = VALUES(status),
                            updated_at = NOW()
                    """, [record_id])
                except Exception as backup_err:
                    logger.warning(f"Agent backup warning for agent {record_id}: {backup_err}")

                # 3. Suspend linked user account. By email: agents.user_id is the
                # Django auth_user id, so "WHERE id = user_id" suspended whichever
                # person had that users id.
                if agent_email:
                    cursor.execute("UPDATE users SET status = 'suspended' WHERE LOWER(email) = LOWER(%s)", [agent_email])
                
                # 4. Delete the agent record with foreign key check guard
                cursor.execute("SET FOREIGN_KEY_CHECKS=0")
                try:
                    cursor.execute("DELETE FROM registration_activity_logs WHERE agent_id = %s", [record_id])
                    # No completed payments here: remove its unpaid checkout rows too.
                    cursor.execute("DELETE FROM agent_subscriptions WHERE agent_id = %s", [record_id])
                    cursor.execute("DELETE FROM agents WHERE id = %s", [record_id])
                finally:
                    cursor.execute("SET FOREIGN_KEY_CHECKS=1")

            elif model == 'agent_draft':
                cursor.execute("SELECT id, fullname, email, mobile, agent_pincode FROM agent_drafts WHERE id = %s", [record_id])
                draft_row = cursor.fetchone()
                if not draft_row:
                    return JsonResponse({'success': False, 'message': 'Draft not found'}, status=404)
                
                cols_draft = ['id', 'fullname', 'email', 'mobile', 'agent_pincode']
                snapshot = dict(zip(cols_draft, [str(v) if v is not None else '' for v in draft_row]))
                
                cursor.execute("SET FOREIGN_KEY_CHECKS=0")
                try:
                    cursor.execute("DELETE FROM registration_activity_logs WHERE draft_id = %s", [record_id])
                    cursor.execute("DELETE FROM agent_drafts WHERE id = %s", [record_id])
                finally:
                    cursor.execute("SET FOREIGN_KEY_CHECKS=1")

            elif model == 'user':
                cursor.execute("SELECT id, role, fullname, email, status FROM users WHERE id = %s", [record_id])
                user_row = cursor.fetchone()
                if not user_row:
                    return JsonResponse({'success': False, 'message': 'Record not found'}, status=404)
                
                user_role = user_row[1]
                cols_user = ['id', 'role', 'fullname', 'email', 'status']
                snapshot = dict(zip(cols_user, [str(v) if v is not None else '' for v in user_row]))
                
                if user_role == 'distributor':
                    # Distributor Deletion: Suspend the user and remove from Distributors module
                    # by changing the role, ensuring they remain in the Users module.
                    cursor.execute("UPDATE users SET status = 'suspended' WHERE id = %s", [record_id])
                    cursor.execute("UPDATE users SET role = 'client' WHERE id = %s", [record_id])
                else:
                    # Generic User hard-delete behavior
                    cursor.execute("DELETE FROM users WHERE id = %s", [record_id])

            elif model == 'lead':
                cursor.execute("SELECT id, agent_id, name, phone, email, notes, created_at FROM agent_leads WHERE id = %s", [record_id])
                lead_row = cursor.fetchone()
                if lead_row:
                    cols_lead = ['id', 'agent_id', 'name', 'phone', 'email', 'notes', 'created_at']
                    snapshot = dict(zip(cols_lead, [str(v) if v is not None else '' for v in lead_row]))
                cursor.execute("DELETE FROM agent_leads WHERE id = %s", [record_id])

            elif model == 'promo_code':
                cursor.execute("SELECT id, code, discount_percent, max_uses, uses_count, is_active FROM promo_codes WHERE id = %s", [record_id])
                promo_row = cursor.fetchone()
                if promo_row:
                    cols_promo = ['id', 'code', 'discount_percent', 'max_uses', 'uses_count', 'is_active']
                    snapshot = dict(zip(cols_promo, [str(v) if v is not None else '' for v in promo_row]))
                cursor.execute("DELETE FROM promo_codes WHERE id = %s", [record_id])

            elif model == 'Faq':
                cursor.execute("SELECT id, question, answer, is_active FROM faqs WHERE id = %s", [record_id])
                faq_row = cursor.fetchone()
                if faq_row:
                    cols_faq = ['id', 'question', 'answer', 'is_active']
                    snapshot = dict(zip(cols_faq, [str(v) if v is not None else '' for v in faq_row]))
                cursor.execute("DELETE FROM faqs WHERE id = %s", [record_id])

            else:
                return JsonResponse({'success': False, 'message': 'Invalid model type'}, status=400)

        # Log the deletion with complete snapshot
        logger.info(f"Admin deleted record: model={model}, record_id={record_id}, admin_id={admin_id}, ip={request.META.get('REMOTE_ADDR')}")
        _log_delete(request, model, record_id, 'deleted', snapshot=snapshot, severity="CRITICAL")

        return JsonResponse({
            'success': True,
            'message': 'Record deleted successfully'
        })
    except Exception as e:
        logger.error(f"Admin delete failed: {e}")
        return JsonResponse({
            'success': False,
            'message': 'Failed to delete record: ' + str(e)
        }, status=500)
