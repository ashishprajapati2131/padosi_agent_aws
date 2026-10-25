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


def _get_config():
    """Read OpenWA connection settings from environment."""
    return {
        'base_url': os.environ.get('WA_BOT_OPENWA_BASE_URL', 'http://localhost:3000').rstrip('/'),
        'session_id': os.environ.get('WA_BOT_OPENWA_SESSION_ID', 'default'),
        'api_key': os.environ.get('WA_BOT_OPENWA_API_KEY', ''),
    }


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


def send_text_message(phone_number, text):
    """
    Send a text message to a WhatsApp number via OpenWA API.

    Args:
        phone_number: Phone number (e.g., '919876543210')
        text: Message text (supports WhatsApp formatting: *bold*, _italic_)

    Returns:
        dict with 'success' (bool) and 'data' or 'error' keys
    """
    config = _get_config()
    chat_id = _format_chat_id(phone_number)
    url = f"{config['base_url']}/sessions/{config['session_id']}/messages/send-text"

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
