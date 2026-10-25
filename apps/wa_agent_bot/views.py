"""
WhatsApp Agent Bot — Webhook Views

Receives incoming WhatsApp messages from OpenWA via webhook,
processes them through the state machine, and sends replies.
"""

import hashlib
import hmac
import json
import logging
import os
import time

from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.core.cache import cache
from django.utils import timezone

from .models import WaBotSession, WaBotMessageLog
from .services.state_machine import process_message
from .services.message_sender import send_text_message

logger = logging.getLogger(__name__)

# ── Rate limiting ───────────────────────────────────────────────────────
RATE_LIMIT_PER_PHONE = 10  # max messages per minute per phone
RATE_LIMIT_WINDOW = 60     # window in seconds


def _check_rate_limit(phone_number):
    """Check if the phone number has exceeded the rate limit."""
    key = f"wa_bot_rl_{phone_number}"
    timestamps = cache.get(key, [])
    now = time.time()
    timestamps = [t for t in timestamps if t > now - RATE_LIMIT_WINDOW]

    if len(timestamps) >= RATE_LIMIT_PER_PHONE:
        return False

    timestamps.append(now)
    cache.set(key, timestamps, timeout=RATE_LIMIT_WINDOW)
    return True


def _verify_webhook_signature(request):
    """
    Verify the HMAC signature of the incoming webhook.
    Returns True if valid or if verification is disabled.
    """
    secret = os.environ.get('WA_BOT_WEBHOOK_SECRET', '')
    if not secret:
        # No secret configured — skip verification (dev mode)
        return True

    signature = request.headers.get('X-Webhook-Signature', '')
    if not signature:
        logger.warning("[WA-Bot] Missing webhook signature header")
        return False

    body = request.body
    expected = hmac.new(
        secret.encode('utf-8'),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


def _extract_message_data(payload):
    """
    Extract phone number and message text from the webhook payload.
    Supports multiple payload formats from OpenWA.

    Returns:
        tuple: (phone_number, message_text, message_type) or (None, None, None) on failure
    """
    # Format 1: Direct event data (from webhook service)
    # { "event": "message:received", "data": { "from": "919876543210@c.us", "body": "hello", ... } }
    data = payload.get('data', payload)

    # Extract phone number
    phone = None
    for key in ('from', 'chatId', 'sender', 'phone', 'phone_number'):
        val = data.get(key)
        if val:
            phone = val
            break

    if not phone:
        # Try nested contact
        contact = data.get('contact', {})
        phone = contact.get('id') or contact.get('phone')

    if not phone:
        return None, None, None

    # Clean phone number (remove @c.us suffix and non-digits)
    phone = str(phone).replace('@c.us', '').replace('@s.whatsapp.net', '')
    phone = ''.join(c for c in phone if c.isdigit())

    # Extract message text
    text = None
    for key in ('body', 'text', 'message', 'content'):
        val = data.get(key)
        if val:
            text = str(val).strip()
            break

    if not text:
        return phone, None, None

    # Extract message type
    msg_type = data.get('type', 'text')

    return phone, text, msg_type


def is_wa_bot_enabled():
    """
    Check if WhatsApp bot service is enabled.
    Priority:
      1. SiteSetting 'wa_agent_bot_enabled' in DB (configured via Admin Panel)
      2. Environment variable 'WA_BOT_ENABLED' (defaults to 'true')
    """
    try:
        from apps.home.models.site_setting import SiteSetting
        val = SiteSetting.get_value('wa_agent_bot_enabled')
        if val is not None:
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ('true', '1', 'yes', 't')
            return bool(val)
    except Exception as e:
        logger.debug(f"[WA-Bot] Could not read SiteSetting: {e}")

    return os.environ.get('WA_BOT_ENABLED', 'true').lower() in ('true', '1', 'yes', 't')


@csrf_exempt
@require_POST
def webhook_receiver(request):
    """
    Main webhook endpoint — receives WhatsApp messages from OpenWA.

    POST /wa-bot/webhook/

    Expected payload from OpenWA webhook:
    {
        "event": "message:received",
        "data": {
            "from": "919876543210@c.us",
            "body": "hello",
            "type": "chat",
            ...
        }
    }
    """
    # ── Check if bot is enabled ─────────────────────────────────────
    if not is_wa_bot_enabled():
        return JsonResponse({'status': 'disabled', 'message': 'WhatsApp Bot is paused via Admin Panel'}, status=200)

    # ── Verify webhook signature ────────────────────────────────────
    if not _verify_webhook_signature(request):
        logger.warning("[WA-Bot] Invalid webhook signature — rejecting request")
        return JsonResponse({'error': 'Invalid signature'}, status=403)

    # ── Parse payload ───────────────────────────────────────────────
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # Check event type — only process incoming messages
    event = payload.get('event', '')
    if event and event not in ('message:received', 'message', 'chat'):
        # Not a message event — acknowledge and ignore
        return JsonResponse({'status': 'ignored', 'reason': f'event type: {event}'}, status=200)

    # ── Extract message data ────────────────────────────────────────
    phone, text, msg_type = _extract_message_data(payload)

    if not phone:
        logger.debug("[WA-Bot] Could not extract phone number from payload")
        return JsonResponse({'error': 'Missing phone number'}, status=400)

    if not text:
        # Non-text message (image, audio, etc.) — politely ignore
        logger.debug(f"[WA-Bot] Non-text message from {phone} (type={msg_type})")
        return JsonResponse({'status': 'ignored', 'reason': 'non-text message'}, status=200)

    # ── Rate limiting ───────────────────────────────────────────────
    if not _check_rate_limit(phone):
        logger.warning(f"[WA-Bot] Rate limit exceeded for {phone}")
        send_text_message(phone, "⚠️ You're sending messages too quickly. Please wait a moment and try again.")
        return JsonResponse({'status': 'rate_limited'}, status=429)

    # ── Get or create session ───────────────────────────────────────
    session, created = WaBotSession.objects.get_or_create(
        phone_number=phone,
        defaults={
            'state': WaBotSession.STATE_WELCOME,
            'registration_data': {},
            'session_context': {},
        },
    )

    if created:
        logger.info(f"[WA-Bot] New session created for {phone}")

    # ── Update activity tracking ────────────────────────────────────
    session.update_last_activity()

    # ── Log incoming message ────────────────────────────────────────
    WaBotMessageLog.objects.create(
        session=session,
        direction=WaBotMessageLog.DIRECTION_IN,
        content=text[:2000],  # cap at 2000 chars
        state_at_time=session.state,
    )

    # ── Process through state machine ───────────────────────────────
    try:
        reply = process_message(session, text)
    except Exception as e:
        logger.error(f"[WA-Bot] Error processing message from {phone}: {e}", exc_info=True)
        reply = (
            "😔 Sorry, something went wrong on our end.\n"
            "Please try again in a moment or type *restart* to start over."
        )

    # ── Log outgoing message ────────────────────────────────────────
    WaBotMessageLog.objects.create(
        session=session,
        direction=WaBotMessageLog.DIRECTION_OUT,
        content=reply[:5000],  # cap at 5000 chars
        state_at_time=session.state,
    )

    # ── Save session (state machine already saved, but ensure) ──────
    session.save()

    # ── Send reply via OpenWA ───────────────────────────────────────
    send_result = send_text_message(phone, reply)

    if not send_result['success']:
        logger.error(f"[WA-Bot] Failed to send reply to {phone}: {send_result.get('error', 'unknown')}")

    return JsonResponse({
        'status': 'processed',
        'phone': phone,
        'state': session.state,
        'message_sent': send_result['success'],
    })


@require_GET
def bot_health(request):
    """
    Health check endpoint for the WhatsApp bot.
    GET /wa-bot/health/
    """
    enabled = is_wa_bot_enabled()
    total_sessions = WaBotSession.objects.count()
    registered_sessions = WaBotSession.objects.filter(is_registered=True).count()

    return JsonResponse({
        'status': 'healthy',
        'enabled': enabled,
        'total_sessions': total_sessions,
        'registered_agents': registered_sessions,
    })


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """
    Razorpay Webhook endpoint for automated WhatsApp Bot payment processing.
    POST /wa-bot/razorpay-webhook/

    Handles events:
      - payment_link.paid
      - order.paid
      - payment.captured
    """
    from apps.agents.models import AgentSubscription
    from apps.agents.services.razorpay_checkout import razorpay_client, razorpay_webhook_secret
    from .services.payment_service import activate_agent_subscription_after_payment

    raw_body = request.body.decode('utf-8')
    signature = request.headers.get('X-Razorpay-Signature', '')
    secret = razorpay_webhook_secret()

    # Verify signature if secret configured
    if secret and signature:
        client = razorpay_client()
        if client:
            try:
                client.utility.verify_webhook_signature(raw_body, signature, secret)
            except Exception as e:
                logger.error(f"[WA-Bot-Razorpay] Webhook signature verification failed: {e}")
                return JsonResponse({'status': 'error', 'message': 'Invalid signature'}, status=400)

    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    event = data.get('event', '')
    logger.info(f"[WA-Bot-Razorpay] Webhook event received: {event}")

    # Extract payment / link details
    payload = data.get('payload', {})
    plink_entity = payload.get('payment_link', {}).get('entity', {})
    payment_entity = payload.get('payment', {}).get('entity', {})
    order_entity = payload.get('order', {}).get('entity', {})

    notes = plink_entity.get('notes') or payment_entity.get('notes') or order_entity.get('notes') or {}
    subscription_id = notes.get('subscription_id')
    payment_id = payment_entity.get('id') or plink_entity.get('id')

    sub = None
    if subscription_id:
        sub = AgentSubscription.objects.filter(pk=subscription_id).first()

    if not sub:
        # Try matching by payment link ID or order ID
        link_id = plink_entity.get('id') or order_entity.get('id')
        if link_id:
            sub = AgentSubscription.objects.filter(razorpay_order_id=link_id).first()

    if sub:
        success, msg = activate_agent_subscription_after_payment(sub.id, payment_id=payment_id, signature=signature)
        logger.info(f"[WA-Bot-Razorpay] Activation result for sub #{sub.id}: {msg}")
        return JsonResponse({'status': 'success', 'message': msg})
    else:
        logger.warning(f"[WA-Bot-Razorpay] Could not match subscription for event {event}")
        return JsonResponse({'status': 'ignored', 'message': 'Subscription not found'})


@require_GET
def payment_callback(request):
    """
    Payment Link return callback URL.
    GET /wa-bot/payment-callback/?razorpay_payment_id=...&razorpay_payment_link_id=...&razorpay_payment_link_status=paid
    """
    from apps.agents.models import AgentSubscription
    from .services.payment_service import activate_agent_subscription_after_payment

    payment_id = request.GET.get('razorpay_payment_id', '')
    link_id = request.GET.get('razorpay_payment_link_id', '')
    link_status = request.GET.get('razorpay_payment_link_status', '')
    signature = request.GET.get('razorpay_signature', '')

    site_url = os.environ.get('WA_BOT_SITE_URL', os.environ.get('APP_URL', 'http://localhost:8000')).rstrip('/')
    login_url = f"{site_url}/agent-login/"

    if link_id:
        sub = AgentSubscription.objects.filter(razorpay_order_id=link_id).first()
        if sub:
            activate_agent_subscription_after_payment(sub.id, payment_id=payment_id, signature=signature)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Successful — Padosi Agent</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: 'Plus Jakarta Sans', sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
        }}
        .card {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 24px;
            padding: 40px 32px;
            max-width: 440px;
            width: 90%;
            text-align: center;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }}
        .icon-box {{
            width: 80px;
            height: 80px;
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 38px;
            margin-bottom: 24px;
            box-shadow: 0 10px 25px -5px rgba(16, 185, 129, 0.4);
        }}
        h1 {{
            font-size: 26px;
            font-weight: 800;
            margin: 0 0 12px 0;
            background: linear-gradient(90deg, #ffffff, #cbd5e1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        p {{
            font-size: 15px;
            color: #94a3b8;
            line-height: 1.6;
            margin: 0 0 24px 0;
        }}
        .badge {{
            display: inline-block;
            background: rgba(37, 211, 102, 0.15);
            border: 1px solid #25D366;
            color: #25D366;
            padding: 8px 16px;
            border-radius: 50px;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 24px;
        }}
        .btn {{
            display: block;
            width: 100%;
            padding: 14px 0;
            background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
            color: #ffffff;
            text-decoration: none;
            border-radius: 14px;
            font-weight: 700;
            font-size: 15px;
            transition: all 0.2s ease;
            box-sizing: border-box;
            box-shadow: 0 10px 20px -5px rgba(79, 70, 229, 0.4);
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 15px 25px -5px rgba(79, 70, 229, 0.6);
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon-box">✓</div>
        <h1>Payment Successful!</h1>
        <div class="badge">💬 WhatsApp Credentials Sent</div>
        <p>Your agent account is now active! We have sent your <strong>Login User ID</strong> and <strong>Temporary Password</strong> directly to your WhatsApp.</p>
        <a href="{login_url}" class="btn">Proceed to Agent Login →</a>
    </div>
</body>
</html>"""
    return HttpResponse(html_content, content_type='text/html')
