"""
WhatsApp Agent Bot — Message Sender

Sends WhatsApp messages by calling the OpenWA REST API.
All outgoing messages go through this module for consistent
error handling, logging, and rate control.
"""

import logging
import os
import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


from apps.wa_agent_bot.services.openwa_admin_service import get_openwa_config


def _get_config():
    """Read OpenWA connection settings from DB SiteSetting or environment."""
    return get_openwa_config()


def _build_headers(api_key):
    """Build request headers with optional API key auth."""
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    if api_key:
        headers['X-API-Key'] = api_key
    return headers


def _format_chat_id(phone_number):
    """
    Convert a phone number to WhatsApp chat ID format.
    Input: '919876543210' or '9876543210'
    Output: '919876543210@c.us'
    """
    # Strip any non-digit characters
    digits = ''.join(c for c in phone_number if c.isdigit())
    # Add country code if not present
    if len(digits) == 10:
        digits = '91' + digits
    # Ensure @c.us suffix
    if not digits.endswith('@c.us'):
        digits = digits + '@c.us'
    return digits


def _log_outbound(phone_number, text, category, session, result):
    """Record every outbound attempt (sent or failed) for the admin WhatsApp logs. Never raises."""
    try:
        from apps.wa_agent_bot.models import WaBotSession, WaBotMessageLog
        digits = ''.join(c for c in str(phone_number) if c.isdigit())
        if session is None and digits:
            session = WaBotSession.objects.filter(phone_number=digits).only('id', 'state').first()
        WaBotMessageLog.objects.create(
            session=session,
            phone_number=digits[:20],
            direction=WaBotMessageLog.DIRECTION_OUT,
            category=category,
            status=WaBotMessageLog.STATUS_SENT if result.get('success') else WaBotMessageLog.STATUS_FAILED,
            error=(result.get('error') or '')[:500],
            content=text[:5000],
            state_at_time=getattr(session, 'state', '') or '',
        )
    except Exception as e:
        logger.error(f"[WA-Bot] Could not write message log for {phone_number}: {e}")


def send_text_message(phone_number, text, category='bot', session=None):
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
    if not config['base_url'] or not config['session_id']:
        return {'success': False, 'error': 'OpenWA Server URL / Session ID not configured'}
    chat_id = _format_chat_id(phone_number)
    base = config['base_url'].rstrip('/')
    if not base.endswith('/api'):
        base = f"{base}/api"
    url = f"{base}/sessions/{config['session_id']}/messages/send-text"

    payload = {
        'chatId': chat_id,
        'text': text,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=_build_headers(config['api_key']),
            timeout=30,
        )

        if response.status_code in (200, 201):
            logger.info(f"[WA-Bot] Message sent to {phone_number} (len={len(text)})")
            return {'success': True, 'data': response.json() if response.text else {}}
        else:
            error_msg = f"OpenWA API error: HTTP {response.status_code}"
            try:
                error_data = response.json()
                error_msg += f" — {error_data.get('message', response.text[:200])}"
            except Exception:
                error_msg += f" — {response.text[:200]}"
            logger.error(f"[WA-Bot] Failed to send message to {phone_number}: {error_msg}")
            return {'success': False, 'error': error_msg}

    except RequestException as e:
        error_msg = f"Network error sending to {phone_number}: {str(e)}"
        logger.error(f"[WA-Bot] {error_msg}")
        return {'success': False, 'error': error_msg}
    except Exception as e:
        error_msg = f"Unexpected error sending to {phone_number}: {str(e)}"
        logger.error(f"[WA-Bot] {error_msg}")
        return {'success': False, 'error': error_msg}


def send_multi_line_message(phone_number, lines):
    """
    Send a multi-line message (joins lines with newline).

    Args:
        phone_number: Phone number
        lines: List of strings to join

    Returns:
        dict with 'success' and 'data' or 'error'
    """
    text = '\n'.join(lines)
    return send_text_message(phone_number, text)
