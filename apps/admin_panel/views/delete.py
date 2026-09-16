import logging
import json
from django.db import connection
from django.http import JsonResponse
from .dashboard import _get_admin_from_session

logger = logging.getLogger(__name__)

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

    try:
        with connection.cursor() as cursor:
            if model == 'agent':
                # 1. Fetch agent details
                cursor.execute("SELECT id, user_id FROM agents WHERE id = %s", [record_id])
                agent_row = cursor.fetchone()
                if not agent_row:
                    return JsonResponse({'success': False, 'message': 'Record not found'}, status=404)
                user_id = agent_row[1]
                
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

                # 3. Suspend linked user account
                if user_id:
                    cursor.execute("UPDATE users SET status = 'suspended' WHERE id = %s", [user_id])
                
                # 4. Delete the agent record with foreign key check guard
                cursor.execute("SET FOREIGN_KEY_CHECKS=0")
                try:
                    cursor.execute("DELETE FROM registration_activity_logs WHERE agent_id = %s", [record_id])
                    cursor.execute("DELETE FROM agents WHERE id = %s", [record_id])
                finally:
                    cursor.execute("SET FOREIGN_KEY_CHECKS=1")

            elif model == 'agent_draft':
                cursor.execute("SELECT id FROM agent_drafts WHERE id = %s", [record_id])
                if not cursor.fetchone():
                    return JsonResponse({'success': False, 'message': 'Draft not found'}, status=404)
                
                cursor.execute("SET FOREIGN_KEY_CHECKS=0")
                try:
                    cursor.execute("DELETE FROM registration_activity_logs WHERE draft_id = %s", [record_id])
                    cursor.execute("DELETE FROM agent_drafts WHERE id = %s", [record_id])
                finally:
                    cursor.execute("SET FOREIGN_KEY_CHECKS=1")

            elif model == 'user':
                cursor.execute("SELECT id, role FROM users WHERE id = %s", [record_id])
                user_row = cursor.fetchone()
                if not user_row:
                    return JsonResponse({'success': False, 'message': 'Record not found'}, status=404)
                
                user_role = user_row[1]
                
                if user_role == 'distributor':
                    # Distributor Deletion: Suspend the user and remove from Distributors module
                    # by changing the role, ensuring they remain in the Users module.
                    cursor.execute("UPDATE users SET status = 'suspended' WHERE id = %s", [record_id])
                    cursor.execute("UPDATE users SET role = 'client' WHERE id = %s", [record_id])
                else:
                    # Generic User hard-delete behavior
                    cursor.execute("DELETE FROM users WHERE id = %s", [record_id])

            elif model == 'lead':
                cursor.execute("DELETE FROM agent_leads WHERE id = %s", [record_id])

            elif model == 'promo_code':
                cursor.execute("DELETE FROM promo_codes WHERE id = %s", [record_id])

            elif model == 'Faq':
                cursor.execute("DELETE FROM faqs WHERE id = %s", [record_id])

            else:
                return JsonResponse({'success': False, 'message': 'Invalid model type'}, status=400)

        # Log the deletion
        logger.info(f"Admin deleted record: model={model}, record_id={record_id}, admin_id={admin_id}, ip={request.META.get('REMOTE_ADDR')}")

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
