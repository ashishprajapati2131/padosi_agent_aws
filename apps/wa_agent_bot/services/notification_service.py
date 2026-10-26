"""
WhatsApp Agent Bot — Notification Service

Handles system-triggered notifications sent to agents on WhatsApp,
such as Admin Approval or Admin Rejection notices.
"""

import logging
import os
from django.utils import timezone

logger = logging.getLogger(__name__)


def notify_agent_approved_whatsapp(agent_id):
    """
    Called when an admin approves an agent (status pending_approval -> active).
    Sends a WhatsApp congratulations message with live links to public profile,
    digital visiting card, and agent dashboard.
    """
    from apps.agents.models import Agent
    from apps.wa_agent_bot.models import WaBotSession
    from apps.wa_agent_bot.services.message_sender import send_text_message
    from apps.wa_agent_bot.views import is_wa_bot_enabled

    try:
        if not is_wa_bot_enabled():
            logger.info("[WA-Bot-Notification] WA bot is disabled; skipping approval notification.")
            return False, "WA Bot is disabled"

        agent = Agent.objects.filter(pk=agent_id).first()
        if not agent:
            logger.warning(f"[WA-Bot-Notification] Agent #{agent_id} not found.")
            return False, "Agent not found"

        # Find session or target phone
        session = WaBotSession.objects.filter(agent_id=agent.id).first() if getattr(agent, 'id', None) else None
        target_phone = None
        if session and session.phone_number:
            target_phone = session.phone_number
        elif agent.mobile:
            mobile_digits = ''.join(c for c in agent.mobile if c.isdigit())
            target_phone = ('91' + mobile_digits) if len(mobile_digits) == 10 else mobile_digits

        if not target_phone:
            logger.warning(f"[WA-Bot-Notification] No phone number found for agent #{agent_id}.")
            return False, "No phone number found"

        site_url = os.environ.get('WA_BOT_SITE_URL', os.environ.get('APP_URL', 'http://localhost:8000')).rstrip('/')
        dashboard_url = f"{site_url}/agent/dashboard/"

        # Get profile slug
        profile = agent.get_primary_profile()
        slug = profile.slug if (profile and profile.slug) else str(agent.id)
        profile_url = f"{site_url}/profile/{slug}/"
        card_url = f"{site_url}/card/{slug}/"

        approval_msg = (
            f"🎉 *Congratulations, {agent.fullname}!* 🌟\n\n"
            f"Great news! Your PadosiAgent account has been *APPROVED* by our admin team! 🚀\n"
            f"Your public profile and digital visiting card are now *LIVE* and visible to clients.\n\n"
            f"🌐 *Public Profile Link:*\n{profile_url}\n\n"
            f"📇 *Digital Visiting Card:*\n{card_url}\n\n"
            f"📊 *Agent Dashboard:*\n{dashboard_url}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👉 *Next Steps:*\n"
            f"1. Share your Digital Visiting Card with clients on WhatsApp & Social Media\n"
            f"2. Log in to your dashboard to view customer leads and reviews\n\n"
            f"💬 *WhatsApp Agent Assistant is Ready!*\n"
            f"Type *card* to view your visiting card link, or *help* for all commands."
        )

        # Update session state if session exists
        if session:
            session.is_registered = True
            session.is_logged_in = True
            session.state = WaBotSession.STATE_LOGGED_IN
            session.save()

        # Send via OpenWA
        send_res = send_text_message(target_phone, approval_msg, category='approval', session=session)
        if send_res.get('success'):
            logger.info(f"[WA-Bot-Notification] Sent approval notification to {target_phone} for agent #{agent.id}")
            return True, "Notification sent"
        else:
            logger.warning(f"[WA-Bot-Notification] Failed sending approval notification to {target_phone}: {send_res.get('error')}")
            return False, send_res.get('error')

    except Exception as e:
        logger.error(f"[WA-Bot-Notification] Error notifying approved agent #{agent_id}: {e}")
        return False, str(e)


def notify_agent_rejected_whatsapp(agent_id, reason=None):
    """
    Called when an admin rejects an agent.
    Sends an informative notification message.
    """
    from apps.agents.models import Agent
    from apps.wa_agent_bot.models import WaBotSession
    from apps.wa_agent_bot.services.message_sender import send_text_message
    from apps.wa_agent_bot.views import is_wa_bot_enabled

    try:
        if not is_wa_bot_enabled():
            return False, "WA Bot is disabled"

        agent = Agent.objects.filter(pk=agent_id).first()
        if not agent:
            return False, "Agent not found"

        session = WaBotSession.objects.filter(agent_id=agent.id).first() if getattr(agent, 'id', None) else None
        target_phone = None
        if session and session.phone_number:
            target_phone = session.phone_number
        elif agent.mobile:
            mobile_digits = ''.join(c for c in agent.mobile if c.isdigit())
            target_phone = ('91' + mobile_digits) if len(mobile_digits) == 10 else mobile_digits

        if not target_phone:
            return False, "No phone number found"

        reason_text = f"\n*Reason:* {reason}\n" if reason else ""
        msg = (
            f"Dear {agent.fullname},\n\n"
            f"Your application on PadosiAgent has been reviewed by the admin team."
            f"{reason_text}\n"
            f"Status: *Not Approved / Action Required*\n\n"
            f"Please reach out to our support team at support@padosiagent.com if you believe this is an error or need assistance updating your documents."
        )

        send_text_message(target_phone, msg, category='rejection', session=session)
        return True, "Rejection notification sent"
    except Exception as e:
        logger.error(f"[WA-Bot-Notification] Error notifying rejected agent #{agent_id}: {e}")
        return False, str(e)


LEAD_ALERT_SETTING = 'wa_lead_alert_enabled'


def lead_alerts_enabled():
    """Feature flag (Admin > WhatsApp): send agents a WhatsApp message for every new lead. Off by default."""
    from apps.home.models.site_setting import SiteSetting
    val = SiteSetting.get_value(LEAD_ALERT_SETTING, False)
    if isinstance(val, str):
        return val.strip().lower() in ('true', '1', 'yes', 'on')
    return bool(val)


def notify_agent_new_lead(lead):
    """
    WhatsApp the agent about a new AgentLead. Builds the message in the caller's thread and
    sends it in a background thread so a slow OpenWA server never delays the customer's request.
    Returns True when a send was queued.
    """
    import threading
    from apps.wa_agent_bot.services.message_sender import send_text_message

    try:
        if not lead_alerts_enabled():
            return False
        agent = lead.agent
        digits = ''.join(c for c in (getattr(agent, 'mobile', '') or '') if c.isdigit())
        if len(digits) == 10:
            digits = '91' + digits
        if len(digits) < 11:
            logger.info(f"[WA-Lead-Alert] Agent #{getattr(agent, 'id', None)} has no usable mobile; skipping.")
            return False

        site_url = os.environ.get('WA_BOT_SITE_URL', os.environ.get('APP_URL', 'http://localhost:8000')).rstrip('/')
        lines = [
            "🔔 *New Lead on PadosiAgent!*",
            "",
            f"👤 *Name:* {lead.customer_name or 'Not given'}",
            f"📱 *Mobile:* {lead.customer_mobile or 'Not given'}",
        ]
        if lead.customer_email:
            lines.append(f"📧 *Email:* {lead.customer_email}")
        if lead.insurance_type or lead.service_type:
            lines.append(f"🛡️ *Interested in:* {lead.insurance_type or lead.service_type}")
        if lead.customer_pincode:
            lines.append(f"📍 *Pincode:* {lead.customer_pincode}")
        if lead.enquiry_requirements:
            lines.append(f"📝 *Requirement:* {lead.enquiry_requirements[:300]}")
        lines += ["", f"👉 View all leads: {site_url}/agent/dashboard/", "_Please contact the customer soon._"]
        text = "\n".join(lines)

        def _send():
            from django.db import connection
            try:
                res = send_text_message(digits, text, category='lead_alert')
                if not res.get('success'):
                    logger.warning(f"[WA-Lead-Alert] Failed for lead #{lead.id}: {res.get('error')}")
            finally:
                connection.close()  # this thread opened its own DB connection for the log row

        threading.Thread(target=_send, daemon=True).start()
        return True
    except Exception as e:
        logger.error(f"[WA-Lead-Alert] Error for lead #{getattr(lead, 'id', None)}: {e}")
        return False
