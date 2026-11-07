"""Write flows for the insurance approvals admin views."""

import logging

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.admin_panel.models.agent import Agent
from apps.admin_panel.models.insurance_approval import AgentApprovalRequest
from apps.admin_panel.models.users import User
from apps.agents.models import PaymentStatus

logger = logging.getLogger(__name__)


def process_status_request(request_id, decision, admin_note, admin_id):
    """Apply an approve/reject decision. Returns False if it was already processed."""
    with transaction.atomic():
        # Re-check under a row lock so a double POST can't process the request twice.
        approval_request = AgentApprovalRequest.objects.select_for_update().get(
            pk=request_id
        )
        if not approval_request.is_pending():
            return False
        approval_request.status = decision
        approval_request.admin_note = admin_note
        approval_request.processed_by_id = admin_id
        approval_request.processed_at = timezone.now()
        approval_request.save()

        if decision == "approved":
            agent = approval_request.agent
            new_status = (
                "active" if approval_request.action == "activate" else "inactive"
            )
            agent.status = new_status
            agent.save()
            cache.delete("homepage_reviews")
            logger.info(
                f"Admin approved insurance status change: agent #{agent.id} -> {new_status}"
            )
    return True


def reject_onboarding(agent_id, admin_note, log_action):
    """Reject a pending onboarding. Returns (agent, rejected).

    log_action(action, agent, details) writes the audit row inside the
    transaction; the view supplies it because the log needs the request.
    """
    with transaction.atomic():
        agent = Agent.objects.select_for_update().get(pk=agent_id)
        if agent.status != "pending_admin_approval":
            return agent, False

        agent.status = "rejected"
        agent.admin_notes = f"Rejected Onboarding: {admin_note}"
        agent.save()

        # Deactivate user account
        # By email: agent.user_id is the Django auth_user id, not users.id.
        user = User.objects.filter(email__iexact=agent.email).first()
        if user:
            user.status = "inactive"
            user.save()

        # Deactivate the subscription. The payment itself was received, so
        # it stays 'completed' (marking it 'failed' hid real money from
        # Finance); a refund, if due, is processed separately. A rejected
        # agent cannot open the dashboard (BLOCKED_DASHBOARD_STATUSES).
        from apps.admin_panel.models.agent_subscription import AgentSubscription

        AgentSubscription.objects.filter(
            agent=agent,
            payment_status=PaymentStatus.COMPLETED,
            status="active",
        ).update(status="inactive")

        log_action("Rejected insurance onboarding", agent, admin_note[:500])
    return agent, True
