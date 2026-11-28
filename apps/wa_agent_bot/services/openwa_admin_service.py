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


def _webhooks_api():
    cfg = get_openwa_config()
    base = cfg['base_url'].rstrip('/')
    if not base.endswith('/api'):
        base = f"{base}/api"
    return f"{base}/sessions/{cfg['session_id']}/webhooks"


def _delivery_url(target_webhook_url):
    # OpenWA can't sign requests, so the shared secret rides in the URL.
    secret = os.environ.get('WA_BOT_WEBHOOK_SECRET', '')
    if not secret:
        return target_webhook_url
    return f"{target_webhook_url}{'&' if '?' in target_webhook_url else '?'}{urlencode({'token': secret})}"


def sync_openwa_webhook(target_webhook_url):
    """
    Make the OpenWA session deliver inbound messages to target_webhook_url, with the secret token.
    Repairs the webhook already pointing here and removes duplicates of it (an old copy without
    the token keeps failing with 403). Webhooks pointing anywhere else are left alone.
    Returns (ok, message, webhook_id).
    """
    url = _webhooks_api()
    delivery_url = _delivery_url(target_webhook_url)
    headers = _get_headers()
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code != 200:
            return False, f"OpenWA refused to list webhooks: HTTP {res.status_code} (check Server URL, Session ID and API key)", None
        ours = [w for w in res.json() if str(w.get('url', '')).split('?')[0] == target_webhook_url and w.get('id')]

        removed = 0
        for extra in ours[1:]:
            if requests.delete(f"{url}/{extra['id']}", headers=headers, timeout=8).status_code in (200, 204):
                removed += 1
        note = f" Removed {removed} duplicate webhook(s)." if removed else ""

        if ours:
            keep = ours[0]
            events = keep.get('events') or []
            healthy = keep.get('url') == delivery_url and keep.get('active') and ('*' in events or 'message.received' in events)
            if healthy:
                return True, f"Webhook already active and delivering to: {target_webhook_url}.{note}", keep['id']
            up = requests.patch(f"{url}/{keep['id']}", json={'url': delivery_url, 'active': True, 'events': ['*']}, headers=headers, timeout=8)
            if up.status_code in (200, 204):
                return True, f"Repaired the OpenWA webhook (URL/token/events) for: {target_webhook_url}.{note}", keep['id']
            return False, f"OpenWA refused to update the webhook: HTTP {up.status_code}", keep['id']

        create_res = requests.post(url, json={'url': delivery_url, 'events': ['*']}, headers=headers, timeout=8)
        if create_res.status_code in (200, 201):
            return True, f"Successfully registered new webhook pointing to: {target_webhook_url}", (create_res.json() or {}).get('id')
        return False, f"Failed to register webhook on OpenWA: HTTP {create_res.status_code}", None
    except Exception as e:
        return False, f"Network error connecting to OpenWA: {e}", None


def run_pipeline_test(target_webhook_url):
    """
    Check every link WhatsApp → OpenWA → this server, repair the webhook, then have OpenWA fire a
    real test delivery at us. Returns {"ok": bool, "steps": [{"name", "ok", "detail"}], "verdict": str}.
    """
    from apps.wa_agent_bot.services import webhook_trace
    from apps.wa_agent_bot.views import is_wa_bot_enabled

    steps = []

    def step(name, ok, detail):
        steps.append({"name": name, "ok": bool(ok), "detail": detail})
        return ok

    def done(verdict):
        return {"ok": all(s["ok"] for s in steps), "steps": steps, "verdict": verdict}

    if not step("Bot master switch", is_wa_bot_enabled(), "ON" if is_wa_bot_enabled() else "OFF"):
        return done("Turn the bot ON with the Bot button at the top of this page, then run the test again.")

    secret = os.environ.get('WA_BOT_WEBHOOK_SECRET', '').strip()
    if not step("Webhook secret on this server", secret, "set" if secret else "WA_BOT_WEBHOOK_SECRET is missing"):
        return done("Add WA_BOT_WEBHOOK_SECRET to this server's .env, restart the app, then run the test again.")

    status = get_openwa_session_status()
    if not step("OpenWA server reachable", status.get('online'), status.get('error') or f"{status.get('latency_ms')} ms"):
        return done("This server cannot reach OpenWA. Check Server URL / API key in Server Settings, and that the OpenWA service is running.")
    connected = status.get('is_connected')
    step(
        "WhatsApp session connected",
        connected,
        f"+{status.get('phone')}" if connected and status.get('phone') else f"status: {status.get('status')}",
    )

    ok, message, webhook_id = sync_openwa_webhook(target_webhook_url)
    if not step("Webhook registered in OpenWA", ok, message) or not webhook_id:
        return done("OpenWA would not accept the webhook. Check the Session ID and API key in Server Settings.")

    started = time.time()
    try:
        res = requests.post(f"{_webhooks_api()}/{webhook_id}/test", headers=_get_headers(), timeout=25)
        result = res.json() if res.status_code in (200, 201) else {"success": False, "error": f"OpenWA test call failed: HTTP {res.status_code}"}
    except Exception as e:
        result = {"success": False, "error": f"OpenWA test call failed: {e}"}

    seen = webhook_trace.last_seen() or {}
    arrived = float(seen.get("ts") or 0) >= started
    code = result.get("statusCode")
    if result.get("success"):
        step("OpenWA → this server (test delivery)", True, f"delivered, HTTP {code or 200}")
        if not connected:
            return done("The link works, but the WhatsApp session is not connected: open OpenWA and scan the QR code.")
        return done(
            f"Everything is connected. Send LIAFI from another phone to +{status.get('phone')} "
            "and it will appear under Recent WhatsApp messages."
        )

    detail = f"HTTP {code}" if code else str(result.get("error") or "failed")
    step("OpenWA → this server (test delivery)", False, detail)
    if arrived:
        events = webhook_trace.recent()
        why = events[0]["detail"] if events else "rejected"
        return done(f"The test reached this server but was refused: {why}")
    if code in (403, 429, 503):
        return done(
            f"The test was blocked with HTTP {code} BEFORE it reached this server. That is Cloudflare (or the host firewall) "
            "blocking the OpenWA server. In Cloudflare: Security → WAF → Custom rules → add a rule "
            "'URI Path equals /wa-bot/webhook/' with action Skip (all security features), then run this test again."
        )
    return done(f"OpenWA could not deliver the test ({detail}) and nothing reached this server. Check that OpenWA can reach {target_webhook_url}.")


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
                'is_connected': raw_status in ('connected', 'working', 'authenticated', 'ready'),  # OpenWA 0.12 reports 'ready'
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

    res = send_text_message(clean_phone, text, category='admin_test')
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

