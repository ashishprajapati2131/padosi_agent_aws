"""Write flows for finance mark-payment (views/finance.py)."""

from django.utils.timezone import now

from apps.admin_panel.models.agent_subscription import AgentSubscription
from apps.agents.models import PaymentStatus


def change_payment_status(sub, status):
    """Apply a payment_status change; the caller has done auth and the super-admin check."""
    old_status = sub.payment_status
    if status == "completed" and old_status != "completed":
        # Same steps as every gateway activation (CLAUDE.md invariant 10): plan_type, dates,
        # superseded rows, referral/championship credit. Invoice and email stay manual here.
        from apps.agents.views.registration import _activate_paid_subscription

        payment = {
            "id": sub.razorpay_payment_id,
            "signature": sub.razorpay_signature or "admin_mark_payment",
        }
        _activate_paid_subscription(
            sub.agent,
            sub,
            payment,
            log_label="[Admin mark payment]",
            queue_fulfilment=False,
        )
    elif status != old_status:
        from django.db import transaction
        from apps.agents.models import Agent

        with transaction.atomic():
            sub.payment_status = status
            sub.updated_at = now()
            fields = ["payment_status", "updated_at"]
            if old_status == "completed":
                # Un-completing a payment must also take the access it granted.
                sub.status = "inactive"
                fields.append("status")
            sub.save(update_fields=fields)
            if old_status == "completed":
                still_paid = (
                    AgentSubscription.objects.filter(
                        agent_id=sub.agent_id,
                        payment_status=PaymentStatus.COMPLETED,
                        status="active",
                    )
                    .exclude(pk=sub.pk)
                    .exists()
                )
                if not still_paid:
                    Agent.objects.filter(pk=sub.agent_id, status="active").update(
                        status="pending_payment"
                    )
