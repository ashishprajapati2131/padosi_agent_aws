"""Write flows for admin account-deletion requests (views/account_deletion.py)."""

import logging
from datetime import datetime

from django.db import connection, transaction

from apps.agents.models import Agent

# Same logger name as before the move, so log routing/filters are unchanged.
logger = logging.getLogger("apps.admin_panel.views.account_deletion")


def terminate_account(del_req, admin_id, admin_notes, log_action):
    """log_action(agent, del_req) writes the audit row inside the transaction;
    the view supplies it because the log needs the request. Returns agent."""
    # Resolve Agent
    # Linked agent or exact email only. A mobile fallback let a request carrying someone
    # else's number terminate (or reactivate) that other agent.
    agent = del_req.agent or Agent.objects.filter(email__iexact=del_req.email).first()

    now = datetime.now()

    with transaction.atomic():
        if agent:
            # Remember what reactivation must restore (it used to force 'active' + visible,
            # skipping payment/approval for agents who were still pending).
            profile = getattr(agent, 'profile', None)
            summary = dict(del_req.data_retention_summary or {})
            summary.setdefault('previous_agent_status', agent.status)
            if profile:
                summary.setdefault('previous_profile_visible', bool(profile.is_profile_visible))
                summary.setdefault('previous_card_visible', bool(profile.is_card_visible))
            del_req.data_retention_summary = summary

            # Hide public profile and card while keeping all records intact
            try:
                with transaction.atomic():  # savepoint: a failure here must not break the outer transaction
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
        log_action(agent, del_req)

    return agent


def activate_account(del_req, admin_id, admin_notes, log_action):
    """See terminate_account for log_action. Returns agent."""
    # Resolve Agent
    # Linked agent or exact email only. A mobile fallback let a request carrying someone
    # else's number terminate (or reactivate) that other agent.
    agent = del_req.agent or Agent.objects.filter(email__iexact=del_req.email).first()

    now = datetime.now()
    summary = del_req.data_retention_summary or {}

    with transaction.atomic():
        if agent:
            # Restore public profile and card
            try:
                with transaction.atomic():  # savepoint: a failure here must not break the outer transaction
                    profile = getattr(agent, 'profile', None)
                    if profile:
                        profile.is_profile_visible = summary.get('previous_profile_visible', True)
                        profile.is_card_visible = summary.get('previous_card_visible', True)
                        profile.save(update_fields=['is_profile_visible', 'is_card_visible'])
            except Exception as e:
                logger.warning(f"Error restoring visibility for agent {agent.id}: {e}")

            # Back to the status before termination ('active' for requests terminated before this was recorded)
            agent.status = summary.get('previous_agent_status') or 'active'
            agent.save(update_fields=['status'])

            # Reactivate user account
            if agent.email:
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE users SET status = 'active' WHERE LOWER(email) = LOWER(%s)", [agent.email])

            if agent.user:
                agent.user.is_active = True
                agent.user.save(update_fields=['is_active'])

        # Restored: drop the snapshot so a later termination records the then-current state.
        del_req.data_retention_summary = {k: v for k, v in summary.items() if not k.startswith('previous_')}
        # Reset deletion request status to PENDING or mark as reactivated
        del_req.status = 'PENDING'
        del_req.processed_at = now
        del_req.processed_by_admin_name = f"Admin #{admin_id}"
        del_req.admin_notes = f"{del_req.admin_notes}\n[Admin Reactivated]: {admin_notes}".strip()
        del_req.save()

        # Log admin audit activity
        log_action(agent, del_req)

    return agent


def reject_request(del_req, admin_id, rejection_reason):
    del_req.status = 'REJECTED'
    del_req.rejection_reason = rejection_reason
    del_req.processed_at = datetime.now()
    del_req.processed_by_admin_name = f"Admin #{admin_id}"
    del_req.save()
