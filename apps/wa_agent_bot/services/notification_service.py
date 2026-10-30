"""
WhatsApp Agent Bot — Notification Service

Handles system-triggered notifications sent to agents on WhatsApp,
such as Admin Approval or Admin Rejection notices.
"""

import datetime
import logging
import os
import re
from django.utils import timezone

from apps.wa_agent_bot.services.message_templates import render as render_template
from apps.wa_agent_bot.services.site_url import bot_site_url

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

        site_url = bot_site_url()
        dashboard_url = f"{site_url}/agent/dashboard/"

        # Get profile slug
        profile = agent.get_primary_profile()
        slug = profile.slug if (profile and profile.slug) else str(agent.id)
        profile_url = f"{site_url}/profile/{slug}/"
        card_url = f"{site_url}/card/{slug}/"

        approval_msg = render_template(
            'approval', agent_name=agent.fullname, profile_url=profile_url,
            card_url=card_url, dashboard_url=dashboard_url,
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

        msg = render_template('rejection', agent_name=agent.fullname, reason=reason)

        send_text_message(target_phone, msg, category='rejection', session=session)
        return True, "Rejection notification sent"
    except Exception as e:
        logger.error(f"[WA-Bot-Notification] Error notifying rejected agent #{agent_id}: {e}")
        return False, str(e)


LEAD_ALERT_SETTING = 'wa_lead_alert_enabled'

# Admin > WhatsApp: "someone saw your card / profile" alerts. Off by default.
VIEW_ALERTS_SETTING = 'wa_view_alerts'
VIEW_ALERTS_DEFAULTS = {'card_enabled': False, 'profile_enabled': False, 'top_n': 3}
MAX_VIEW_ALERT_TOP_N = 20

# Crawlers and link-preview fetchers (WhatsApp/Facebook unfurl a shared link) are not clients.
_BOT_UA_RE = re.compile(
    r'bot|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|telegram|curl|wget|python|headless',
    re.IGNORECASE,
)


def _agent_wa_number(agent):
    """Agent mobile as a WhatsApp number (91XXXXXXXXXX), or '' when unusable."""
    digits = ''.join(c for c in (getattr(agent, 'mobile', '') or '') if c.isdigit())
    if len(digits) == 10:
        digits = '91' + digits
    return digits if len(digits) >= 11 else ''


def is_bot_request(request):
    ua = request.META.get('HTTP_USER_AGENT', '') or ''
    return not ua or bool(_BOT_UA_RE.search(ua))


def view_alert_settings():
    """{'card_enabled': bool, 'profile_enabled': bool, 'top_n': int} from SiteSetting, with safe defaults."""
    from apps.home.models.site_setting import SiteSetting
    conf = dict(VIEW_ALERTS_DEFAULTS)
    try:
        val = SiteSetting.get_value(VIEW_ALERTS_SETTING, {})
        if isinstance(val, dict):
            conf['card_enabled'] = bool(val.get('card_enabled'))
            conf['profile_enabled'] = bool(val.get('profile_enabled'))
            conf['top_n'] = min(max(int(val.get('top_n', 3)), 1), MAX_VIEW_ALERT_TOP_N)
    except Exception as e:
        logger.error(f"[WA-View-Alert] Could not read settings: {e}")
    return conf


def send_view_alert(agent_id, kind, pincode=''):
    """
    WhatsApp an active, paid agent that a client saw their card ('card_view_alert') or profile
    ('profile_view_alert'). At most one of each kind per agent per calendar day (resets at midnight).
    Blocking: call from a background thread. Returns True when a message was sent.
    """
    from django.core.cache import cache
    from apps.agents.models import Agent
    from apps.agents.services.account_auth import agent_has_completed_payment
    from apps.wa_agent_bot.models import WaBotMessageLog
    from apps.wa_agent_bot.services.message_sender import send_text_message

    try:
        conf = view_alert_settings()
        if not conf['card_enabled' if kind == 'card_view_alert' else 'profile_enabled']:
            return False
        if kind == 'card_view_alert' and not pincode:
            return False
        agent = Agent.objects.filter(id=agent_id, status='active').first()
        if not agent or not agent_has_completed_payment(agent):
            return False
        digits = _agent_wa_number(agent)
        if not digits:
            return False

        today = datetime.date.today()
        # cache.add closes the race between two views in the same second; the log check survives cache eviction.
        if not cache.add(f'wa_view_alert:{kind}:{agent_id}:{today}', 1, 26 * 3600):
            return False
        if WaBotMessageLog.objects.filter(
            phone_number=digits, category=kind,
            created_at__gte=datetime.datetime.combine(today, datetime.time.min),
        ).exists():
            return False

        text = render_template(
            kind,
            agent_name=getattr(agent, 'fullname', ''),
            pincode=pincode,
            dashboard_url=f"{bot_site_url()}/agent/dashboard/",
        )
        res = send_text_message(digits, text, category=kind)
        if not res.get('success'):
            logger.warning(f"[WA-View-Alert] {kind} failed for agent #{agent_id}: {res.get('error')}")
        return bool(res.get('success'))
    except Exception as e:
        logger.error(f"[WA-View-Alert] {kind} error for agent #{agent_id}: {e}")
        return False


def notify_agent_profile_view(request, agent_id):
    """Queue a profile-view alert unless the visitor is a bot or the feature is off."""
    import threading
    try:
        if is_bot_request(request) or not view_alert_settings()['profile_enabled']:
            return False

        def _run():
            from django.db import connection
            try:
                send_view_alert(agent_id, 'profile_view_alert')
            finally:
                connection.close()

        threading.Thread(target=_run, daemon=True).start()
        return True
    except Exception as e:
        logger.error(f"[WA-View-Alert] Could not queue profile alert for agent #{agent_id}: {e}")
        return False


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
        digits = _agent_wa_number(agent)
        if not digits:
            logger.info(f"[WA-Lead-Alert] Agent #{getattr(agent, 'id', None)} has no usable mobile; skipping.")
            return False

        site_url = bot_site_url()
        email = lead.customer_email or ''
        if email.lower().endswith('@padosiagent.com'):
            email = ''  # placeholder address generated for visitors who gave only a mobile
        text = render_template(
            'lead_alert',
            agent_name=getattr(agent, 'fullname', ''),
            customer_name=lead.customer_name or 'Not given',
            customer_mobile=lead.customer_mobile or 'Not given',
            customer_email=email,
            interested_in=lead.insurance_type or lead.service_type,
            pincode=lead.customer_pincode,
            requirement=(lead.enquiry_requirements or '')[:300],
            dashboard_url=f"{site_url}/agent/dashboard/",
        )

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
