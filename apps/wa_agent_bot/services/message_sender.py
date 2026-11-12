"""
WhatsApp Agent Bot — Message Sender

Sends WhatsApp messages by calling the OpenWA REST API.
All outgoing messages go through this module for consistent
error handling, logging, and rate control.
"""

import logging
import re
import requests
from requests.exceptions import RequestException

# "Password: `xxx`" or "Password: xxx" lines are redacted before logging (audit WA3).
_PASSWORD_LINE_RE = re.compile(r"(?im)^(.*?password[^\n:]*:\s*)(?:`[^`\n]+`|\S+).*$")


def _redact(text):
    if not text:
        return text
    return _PASSWORD_LINE_RE.sub(r"\1[redacted]", text)


logger = logging.getLogger(__name__)


from apps.wa_agent_bot.services.openwa_admin_service import get_openwa_config


def _get_config():
    """Read OpenWA connection settings from DB SiteSetting or environment."""
    return get_openwa_config()


def _build_headers(api_key):
    """Build request headers with optional API key auth."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _format_chat_id(phone_number):
    """
    Convert a phone number to WhatsApp chat ID format.
    Input: '919876543210' or '9876543210'
    Output: '919876543210@c.us'
    """
    # Strip any non-digit characters
    digits = "".join(c for c in phone_number if c.isdigit())
    # Add country code if not present
    if len(digits) == 10:
        digits = "91" + digits
    # Ensure @c.us suffix
    if not digits.endswith("@c.us"):
        digits = digits + "@c.us"
    return digits


def _log_outbound(phone_number, text, category, session, result):
    """Record every outbound attempt (sent or failed) for the admin WhatsApp logs. Never raises."""
    try:
        from apps.wa_agent_bot.models import WaBotSession, WaBotMessageLog

        digits = "".join(c for c in str(phone_number) if c.isdigit())
        if session is None and digits:
            session = (
                WaBotSession.objects.filter(phone_number=digits)
                .only("id", "state")
                .first()
            )
        WaBotMessageLog.objects.create(
            session=session,
            phone_number=digits[:20],
            direction=WaBotMessageLog.DIRECTION_OUT,
            category=category,
            status=WaBotMessageLog.STATUS_SENT
            if result.get("success")
            else WaBotMessageLog.STATUS_FAILED,
            error=(result.get("error") or "")[:500],
            content=_redact(text)[:5000],  # audit WA3: don't log passwords
            state_at_time=getattr(session, "state", "") or "",
        )
    except Exception as e:
        logger.error(f"[WA-Bot] Could not write message log for {phone_number}: {e}")


def send_text_message(phone_number, text, category="bot", session=None):
    """
    Send a text message to a WhatsApp number via OpenWA API and log the attempt.

    Args:
        phone_number: Phone number (e.g., '919876543210')
        text: Message text (supports WhatsApp formatting: *bold*, _italic_)
        category: WaBotMessageLog category ('bot', 'lead_alert', 'approval', ...)
        session: WaBotSession to link the log to (looked up by phone when omitted)

    Returns:
        dict with 'success' (bool) and 'data' or 'error' keys
    """
    result = _send(phone_number, text)
    _log_outbound(phone_number, text, category, session, result)
    return result


def _send(phone_number, text):
    config = _get_config()
    if not config["base_url"] or not config["session_id"]:
        return {
            "success": False,
            "error": "OpenWA Server URL / Session ID not configured",
        }
    chat_id = _format_chat_id(phone_number)
    base = config["base_url"].rstrip("/")
    if not base.endswith("/api"):
        base = f"{base}/api"
    url = f"{base}/sessions/{config['session_id']}/messages/send-text"

    payload = {
        "chatId": chat_id,
        "text": text,
    }
    # OpenWA >= 0.14 on the Baileys engine sends links without the preview card unless asked.
    if "http://" in text or "https://" in text:
        payload["linkPreview"] = True

    try:
        response = requests.post(
            url,
            json=payload,
            headers=_build_headers(config["api_key"]),
            timeout=30,
        )
        if response.status_code == 400 and "linkPreview" in payload:
            # Older OpenWA rejects the unknown field: send the plain text instead of failing.
            logger.warning(
                f"[WA-Bot] linkPreview rejected ({response.text[:120]}); resending without it"
            )
            payload.pop("linkPreview")
            response = requests.post(
                url,
                json=payload,
                headers=_build_headers(config["api_key"]),
                timeout=30,
            )

        if response.status_code in (200, 201):
            logger.info(f"[WA-Bot] Message sent to {phone_number} (len={len(text)})")
            return {"success": True, "data": response.json() if response.text else {}}
        else:
            error_msg = f"OpenWA API error: HTTP {response.status_code}"
            try:
                error_data = response.json()
                error_msg += f" — {error_data.get('message', response.text[:200])}"
            except Exception:
                error_msg += f" — {response.text[:200]}"
            logger.error(
                f"[WA-Bot] Failed to send message to {phone_number}: {error_msg}"
            )
            return {"success": False, "error": error_msg}

    except RequestException as e:
        error_msg = f"Network error sending to {phone_number}: {str(e)}"
        logger.error(f"[WA-Bot] {error_msg}")
        return {"success": False, "error": error_msg}
    except Exception as e:
        error_msg = f"Unexpected error sending to {phone_number}: {str(e)}"
        logger.error(f"[WA-Bot] {error_msg}")
        return {"success": False, "error": error_msg}


CAPTION_MAX = 1024  # WhatsApp/OpenWA limit for a photo caption


def send_image_message(phone_number, image_url, caption, category="bot", session=None):
    """
    Send a photo (fetched by OpenWA from image_url) with a caption, and log it like a text message.
    Used for broadcasts so the agent's profile card always shows, whatever the engine does with link previews.
    """
    result = _send_image(phone_number, image_url, caption)
    _log_outbound(phone_number, caption, category, session, result)
    return result


def _send_image(phone_number, image_url, caption):
    config = _get_config()
    if not config["base_url"] or not config["session_id"]:
        return {
            "success": False,
            "error": "OpenWA Server URL / Session ID not configured",
        }
    base = config["base_url"].rstrip("/")
    if not base.endswith("/api"):
        base = f"{base}/api"
    url = f"{base}/sessions/{config['session_id']}/messages/send-image"
    payload = {
        "chatId": _format_chat_id(phone_number),
        "url": image_url,
        "caption": caption[:CAPTION_MAX],
    }
    try:
        response = requests.post(
            url, json=payload, headers=_build_headers(config["api_key"]), timeout=60
        )
    except RequestException as e:
        logger.error(f"[WA-Bot] Network error sending image to {phone_number}: {e}")
        return {"success": False, "error": f"Network error sending image: {e}"}
    if response.status_code in (200, 201):
        logger.info(f"[WA-Bot] Image sent to {phone_number}")
        return {"success": True, "data": response.json() if response.text else {}}
    error = f"OpenWA API error (send-image): HTTP {response.status_code} — {response.text[:200]}"
    logger.error(f"[WA-Bot] Failed to send image to {phone_number}: {error}")
    return {"success": False, "error": error, "status_code": response.status_code}
