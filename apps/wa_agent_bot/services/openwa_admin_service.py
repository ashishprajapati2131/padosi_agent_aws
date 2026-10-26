"""
OpenWA Admin Management Service — PadosiAgent
==============================================
Provides high-level helpers to query OpenWA server health, session status,
fetch live QR codes for pairing, control session lifecycle (start, stop, restart, logout),
and dispatch administrator test messages directly from the Admin Panel.
"""

import logging
import os
import time
from urllib.parse import urlencode

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


def get_openwa_config():
    """Read OpenWA API configuration from DB SiteSetting or environment."""
    try:
        from apps.home.models.site_setting import SiteSetting
        base_url = SiteSetting.get_value('wa_bot_openwa_base_url') or os.environ.get('WA_BOT_OPENWA_BASE_URL', 'http://localhost:2785')
        session_id = SiteSetting.get_value('wa_bot_openwa_session_id') or os.environ.get('WA_BOT_OPENWA_SESSION_ID', '')
        api_key = SiteSetting.get_value('wa_bot_openwa_api_key') or os.environ.get('WA_BOT_OPENWA_API_KEY', '')
    except Exception:
        base_url = os.environ.get('WA_BOT_OPENWA_BASE_URL', 'http://localhost:2785')
        session_id = os.environ.get('WA_BOT_OPENWA_SESSION_ID', '')
        api_key = os.environ.get('WA_BOT_OPENWA_API_KEY', '')

    return {
        'base_url': str(base_url or '').strip().rstrip('/'),
        'session_id': str(session_id or '').strip(),
        'api_key': str(api_key or '').strip(),
    }


def sync_openwa_webhook(target_webhook_url):
    """
    Ensure the remote OpenWA session delivers inbound messages to target_webhook_url.
    Checks existing webhooks and creates or updates automatically across servers.
    """
    cfg = get_openwa_config()
    session_id = cfg['session_id']
    base = cfg['base_url'].rstrip('/')
    if not base.endswith('/api'):
        base = f"{base}/api"
    url = f"{base}/sessions/{session_id}/webhooks"

    # OpenWA can't sign requests, so the shared secret rides in the URL; messages below show the URL without it.
    secret = os.environ.get('WA_BOT_WEBHOOK_SECRET', '')
    delivery_url = f"{target_webhook_url}{'&' if '?' in target_webhook_url else '?'}{urlencode({'token': secret})}" if secret else target_webhook_url

    headers = _get_headers()
    try:
        # 1. Check existing webhooks
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            existing = res.json()
            for wh in existing:
                if wh.get('url') == delivery_url and wh.get('active'):
                    return True, f"Webhook already active and delivering to: {target_webhook_url}"
                wh_id = wh.get('id')
                if wh_id:
                    up = requests.patch(f"{url}/{wh_id}", json={'url': delivery_url, 'active': True, 'events': ['*']}, headers=headers, timeout=8)
                    if up.status_code in (200, 204):
                        return True, f"Updated existing OpenWA webhook to: {target_webhook_url}"

        # 2. Register new webhook
        create_res = requests.post(url, json={'url': delivery_url, 'events': ['*']}, headers=headers, timeout=8)
        if create_res.status_code in (200, 201):
            return True, f"Successfully registered new webhook pointing to: {target_webhook_url}"
        return False, f"Failed to register webhook on OpenWA: HTTP {create_res.status_code}"
    except Exception as e:
        return False, f"Network error connecting to OpenWA: {e}"


def _get_headers():
    cfg = get_openwa_config()
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    if cfg['api_key']:
        headers['X-API-Key'] = cfg['api_key']
    return headers


def get_openwa_session_status():
    """
    Query OpenWA REST API for current session status.

    Returns dict with:
        online: bool (whether OpenWA server is reachable)
        latency_ms: int
        session: dict or None (session details from OpenWA)
        status: str ('connected', 'qr_ready', 'stopped', 'failed', 'offline')
        phone: str or None
        push_name: str or None
        error: str or None
    """
    cfg = get_openwa_config()
    session_id = cfg['session_id']
    if not session_id or not cfg['base_url']:
        return {
            'online': False, 'latency_ms': 0, 'session': None, 'status': 'not_configured',
            'is_connected': False, 'is_qr_ready': False, 'phone': None, 'push_name': None,
            'error': 'OpenWA Server URL / Session ID not configured (Admin > WhatsApp settings or .env).',
        }
    base = cfg['base_url'].rstrip('/')
    if not base.endswith('/api'):
        base = f"{base}/api"
    url = f"{base}/sessions/{session_id}"

    start_t = time.time()
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=5)
        latency = int((time.time() - start_t) * 1000)

        if resp.status_code == 200:
            data = resp.json()
            raw_status = str(data.get('status', 'unknown')).lower()
            return {
                'online': True,
                'latency_ms': latency,
                'session': data,
                'status': raw_status,
                'is_connected': raw_status in ('connected', 'working', 'authenticated'),
                'is_qr_ready': raw_status in ('qr_ready', 'scan_qr_code'),
                'phone': data.get('phone'),
                'push_name': data.get('pushName'),
                'connected_at': data.get('connectedAt'),
                'last_active': data.get('lastActive'),
                'error': None,
            }
        else:
            return {
                'online': True,
                'latency_ms': latency,
                'session': None,
                'status': 'error',
                'is_connected': False,
                'is_qr_ready': False,
                'phone': None,
                'push_name': None,
                'error': f"HTTP {resp.status_code}: {resp.text[:150]}",
            }
    except RequestException as e:
        latency = int((time.time() - start_t) * 1000)
        return {
            'online': False,
            'latency_ms': latency,
            'session': None,
            'status': 'offline',
            'is_connected': False,
            'is_qr_ready': False,
            'phone': None,
            'push_name': None,
            'error': f"Connection failed: {str(e)[:120]}",
        }


def get_openwa_qr_code():
    """
    Fetch the live QR code data URL for pairing WhatsApp.
    Returns:
        dict with:
            success: bool
            qr_code: str (data:image/png;base64,... or empty)
            status: str
            error: str or None
    """
    cfg = get_openwa_config()
    session_id = cfg['session_id']
    base = cfg['base_url'].rstrip('/')
    if not base.endswith('/api'):
        base = f"{base}/api"
    url = f"{base}/sessions/{session_id}/qr"

    try:
        resp = requests.get(url, headers=_get_headers(), timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            return {
                'success': True,
                'qr_code': data.get('qrCode', ''),
                'status': data.get('status', 'qr_ready'),
                'error': None,
            }
        else:
            return {
                'success': False,
                'qr_code': '',
                'status': 'unavailable',
                'error': f"OpenWA returned HTTP {resp.status_code}",
            }
    except Exception as e:
        return {
            'success': False,
            'qr_code': '',
            'status': 'offline',
            'error': str(e),
        }


def control_openwa_session(action):
    """
    Perform a lifecycle action on the OpenWA session:
      - 'start'
      - 'stop'
      - 'restart'
      - 'logout'
      - 'force_kill'

    Returns:
        tuple (success: bool, message: str)
    """
    cfg = get_openwa_config()
    session_id = cfg['session_id']
    base = cfg['base_url'].rstrip('/')
    if not base.endswith('/api'):
        base = f"{base}/api"

    action = action.lower().strip()
    headers = _get_headers()

    if action == 'restart':
        # Stop then start
        try:
            requests.post(f"{base}/sessions/{session_id}/stop", headers=headers, timeout=10)
            time.sleep(1)
            resp = requests.post(f"{base}/sessions/{session_id}/start", headers=headers, timeout=15)
            if resp.status_code in (200, 201):
                return True, "Session restarted successfully"
            return False, f"Failed to start session after stop: HTTP {resp.status_code}"
        except Exception as e:
            return False, f"Restart error: {e}"

    endpoint_map = {
        'start': f"{base}/sessions/{session_id}/start",
        'stop': f"{base}/sessions/{session_id}/stop",
        'logout': f"{base}/sessions/{session_id}/logout",
        'force_kill': f"{base}/sessions/{session_id}/force-kill",
    }

    url = endpoint_map.get(action)
    if not url:
        return False, f"Unknown action: {action}"

    try:
        resp = requests.post(url, headers=headers, timeout=15)
        if resp.status_code in (200, 201, 204):
            return True, f"Action '{action}' executed successfully"
        else:
            err = resp.text[:150]
            try:
                err = resp.json().get('message', err)
            except Exception:
                pass
            return False, f"OpenWA error: {err}"
    except Exception as e:
        return False, f"Request failed: {e}"


def send_admin_test_whatsapp(phone, text):
    """
    Send a test WhatsApp message from the Admin Panel.
    """
    from apps.wa_agent_bot.services.message_sender import send_text_message
    if not phone or not text:
        return False, "Phone number and text are required"

    clean_phone = ''.join(c for c in phone if c.isdigit())
    if len(clean_phone) < 10:
        return False, "Invalid phone number format"

    res = send_text_message(clean_phone, text)
    if res.get('success'):
        return True, "Message sent successfully!"
    return False, res.get('error', 'Failed to send message via OpenWA')


def _override_url_allowed(url, configured_url):
    """
    An admin-typed OpenWA URL may point at the already-configured host, or at a host that
    resolves only to public addresses — never at internal services or cloud metadata (SSRF).
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in ('http', 'https') or not host:
        return False
    if host == (urlparse(configured_url or '').hostname or '').lower():
        return True
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == 'https' else 80))
    except (socket.gaierror, ValueError):
        return False
    return all(ipaddress.ip_address(info[4][0]).is_global for info in infos)


def list_openwa_sessions(override_base_url=None, override_api_key=None):
    """
    List all sessions configured on the OpenWA server.
    Allows administrators to auto-detect and select the active session ID directly from the UI.
    """
    cfg = get_openwa_config()
    if override_base_url and not _override_url_allowed(override_base_url, cfg['base_url']):
        return False, [], "This OpenWA URL is not allowed (internal or unresolvable host). Save it as the server URL first."
    base = (override_base_url or cfg['base_url']).rstrip('/')
    if not base.endswith('/api'):
        base = f"{base}/api"
    url = f"{base}/sessions"

    api_key = override_api_key if override_api_key is not None else cfg['api_key']
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    if api_key:
        headers['X-API-Key'] = api_key

    try:
        # shortcut: DNS is resolved again by requests (rebinding window); pin the IP if this endpoint is ever exposed beyond admins.
        resp = requests.get(url, headers=headers, timeout=6, allow_redirects=False)
        if resp.status_code == 200:
            return True, resp.json(), None
        # Don't echo bodies from arbitrary hosts back to the browser.
        return False, [], f"HTTP {resp.status_code}"
    except Exception as e:
        return False, [], str(e)

