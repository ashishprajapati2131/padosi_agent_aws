"""Admin broadcasts: one target definition for email + push pages, and background delivery."""

import logging
import threading

from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone
from django.utils.html import escape

from apps.agents.models import Agent, AgentDeviceToken, AgentNotification, PaymentStatus

logger = logging.getLogger(__name__)

TARGETS = {
    "all": "All Active Agents",
    "professional": "Professional's Plan",
    "starter": "Starter's Plan",
    "expiring": "Expiring Soon",
}
_PLAN_TYPES = {
    "professional": ("professional", "pro"),
    # Paid signups store 'starter'; update_plan / Paldi winners store 'basic'.
    "starter": ("starter", "basic", "standard"),
}


def target_agents(target, now=None):
    """Active agents in a broadcast segment. Used by both the email and the push page, which
    used to pick different agents for the same target name."""
    now = now or timezone.now()
    qs = Agent.objects.filter(status="active")
    if target in _PLAN_TYPES:
        plan_q = Q()
        for plan in _PLAN_TYPES[target]:
            plan_q |= Q(plan_type__iexact=plan)
        qs = qs.filter(plan_q)
    elif target == "expiring":
        soon = now + timezone.timedelta(days=30)
        qs = qs.filter(
            Q(trial_ends_at__gte=now, trial_ends_at__lte=soon)
            | Q(
                subscriptions__payment_status=PaymentStatus.COMPLETED,
                subscriptions__expires_at__gte=now,
                subscriptions__expires_at__lte=soon,
            )
        )
    return qs.distinct()


def _email_html(message):
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:30px 0;"><tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);max-width:600px;width:100%;">
      <tr><td style="background:#273C8E;padding:28px 40px;text-align:center;"><h1 style="color:#ffffff;margin:0;font-size:22px;letter-spacing:1px;">PadosiAgent</h1></td></tr>
      <tr><td style="padding:40px 40px 30px; font-size: 14px; color: #475569; line-height: 1.8; white-space: pre-wrap;">{message}</td></tr>
      <tr><td style="background:#f9fafb;padding:20px 40px;text-align:center;border-top:1px solid #e5e7eb;font-size:11px;color:#94a3b8;">PadosiAgent Platform | You're receiving this because you're a registered agent.</td></tr>
    </table>
  </td></tr></table>
</body></html>"""


def deliver_broadcast(broadcast_id, agent_ids, subject, message, channels, target):
    """Send emails / pushes and record the real sent count on the AdminBroadcast row."""
    from apps.admin_panel.models import AdminBroadcast
    from apps.admin_panel.services.brevo import send_brevo_email
    from apps.admin_panel.services.fcm import FcmService

    email_sent = push_sent = 0
    if "email" in channels:
        for agent in Agent.objects.filter(id__in=agent_ids).only(
            "id", "fullname", "email"
        ):
            # Agent names are user-supplied; escape them before they go into the HTML email.
            text = message.replace("[Agent Name]", escape(agent.fullname)).replace(
                "{name}", escape(agent.fullname)
            )
            try:
                if send_brevo_email(
                    agent.email, agent.fullname, subject, _email_html(text)
                ):
                    email_sent += 1
            except Exception:
                logger.exception(
                    "Broadcast #%s: email to agent %s failed", broadcast_id, agent.id
                )

    if "notification" in channels and agent_ids:
        try:
            for i in range(0, len(agent_ids), 500):
                AgentNotification.objects.bulk_create(
                    [
                        AgentNotification(agent_id=a, title=subject, body=message[:191])
                        for a in agent_ids[i : i + 500]
                    ]
                )
        except Exception:
            logger.exception(
                "Broadcast #%s: saving dashboard notifications failed", broadcast_id
            )
        tokens = list(
            AgentDeviceToken.objects.filter(agent_id__in=agent_ids)
            .exclude(token=None)
            .exclude(token="")
            .values_list("token", flat=True)
            .distinct()
        )
        if tokens:
            try:
                push_sent = (
                    FcmService().send_to_tokens(
                        tokens,
                        subject,
                        message[:255],
                        {"type": "admin_broadcast", "target": target},
                    )
                    or 0
                )
            except Exception:
                logger.exception("Broadcast #%s: push send failed", broadcast_id)

    AdminBroadcast.objects.filter(pk=broadcast_id).update(
        sent_count=email_sent + push_sent
    )
    logger.info(
        "Broadcast #%s delivered: %s emails, %s pushes",
        broadcast_id,
        email_sent,
        push_sent,
    )
    return email_sent, push_sent


def queue_broadcast(broadcast_id, agent_ids, subject, message, channels, target):
    """Deliver in a background thread: one email per agent used to run inside the request
    (20 s timeout each), so large targets timed out halfway and a retry re-sent to the first batch."""

    def run():
        close_old_connections()
        try:
            deliver_broadcast(
                broadcast_id, agent_ids, subject, message, channels, target
            )
        except Exception:
            logger.exception("Broadcast #%s failed", broadcast_id)
        finally:
            close_old_connections()

    threading.Thread(
        target=run, daemon=False, name=f"admin-broadcast-{broadcast_id}"
    ).start()
