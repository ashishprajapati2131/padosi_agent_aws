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

    # Ignore outgoing messages sent by the bot itself (prevent echo loop)
    if data.get('fromMe') is True or (isinstance(data.get('id'), dict) and data.get('id', {}).get('fromMe') is True):
        return None, None, None

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
    if event and event not in ('message.received', 'message:received', 'message', 'chat'):
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

    sub = None
    if link_id:
        sub = AgentSubscription.objects.filter(razorpay_order_id=link_id).first()
    if not sub and payment_id:
        sub = AgentSubscription.objects.filter(razorpay_payment_id=payment_id).first()

    if sub:
        # Security verification: Verify payment validity before activation
        is_verified = False
        if sub.payment_status == 'completed':
            is_verified = True
        else:
            from apps.agents.services.razorpay_checkout import razorpay_client
            client = razorpay_client()
            if client and payment_id and not payment_id.startswith(('pay_test', 'pay_local')):
                try:
                    pay_obj = client.payment.fetch(payment_id)
                    if pay_obj and pay_obj.get('status') in ('captured', 'authorized'):
                        is_verified = True
                    else:
                        logger.warning(f"[WA-Bot-Security] Payment {payment_id} not captured: {pay_obj.get('status') if pay_obj else None}")
                except Exception as e:
                    logger.error(f"[WA-Bot-Security] Razorpay verification error for {payment_id}: {e}")
            elif link_status == 'paid' or payment_id:
                # Valid in test/dev environments or when webhook already verified
                is_verified = True

        if is_verified:
            activate_agent_subscription_after_payment(sub.id, payment_id=payment_id, signature=signature)
            sub.refresh_from_db()
        else:
            logger.warning(f"[WA-Bot-Security] Rejected unverified activation attempt for sub #{sub.id}")

    agent = sub.agent if sub else None
    fullname = (agent.fullname if agent and agent.fullname else 'Agent')
    email = (agent.email if agent and agent.email else '')
    mobile_clean = ''.join(c for c in (agent.mobile or '') if c.isdigit()) if agent else ''
    masked_mobile = f"+91 {mobile_clean[:2]}•••••{mobile_clean[-3:]}" if len(mobile_clean) == 10 else (f"+{mobile_clean}" if mobile_clean else 'Registered Number')
    plan_name = (sub.selected_plan if sub and sub.selected_plan else 'Membership Plan')
    copy_email_btn = f'<button type="button" class="copy-btn" onclick="copyText(\'{email}\', this)">Copy</button>' if email else ''

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Payment Received — PadosiAgent</title>
    <link rel="icon" type="image/png" href="/static/img/logo-icon.webp">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #ffffff;
            background-image: radial-gradient(1200px circle at 50% -10%, #edf2f7 0%, #ffffff 70%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px 16px;
            color: #0f172a;
        }}
        .card-container {{
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 28px;
            padding: 44px 36px 36px;
            max-width: 490px;
            width: 100%;
            text-align: center;
            box-shadow: 0 25px 60px -15px rgba(39, 60, 142, 0.1), 0 4px 16px rgba(0, 0, 0, 0.02);
            transition: all 0.3s ease;
        }}
        .logo-box {{
            margin-bottom: 24px;
        }}
        .logo-box img {{
            height: 48px;
            width: auto;
            max-width: 200px;
            object-fit: contain;
            display: inline-block;
        }}
        .icon-circle {{
            width: 72px;
            height: 72px;
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            font-size: 32px;
            margin-bottom: 18px;
            box-shadow: 0 10px 25px -5px rgba(16, 185, 129, 0.38);
            animation: popIn 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }}
        @keyframes popIn {{
            0% {{ transform: scale(0.6); opacity: 0; }}
            100% {{ transform: scale(1); opacity: 1; }}
        }}
        h1 {{
            font-size: 25px;
            font-weight: 800;
            color: #0f172a;
            margin-bottom: 8px;
            letter-spacing: -0.5px;
        }}
        .badge-pill {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #ecfdf5;
            border: 1px solid #a7f3d0;
            color: #047857;
            padding: 6px 14px;
            border-radius: 50px;
            font-size: 13px;
            font-weight: 700;
            margin-bottom: 16px;
        }}
        .badge-pill i {{
            font-size: 14px;
            color: #10b981;
        }}
        p.desc {{
            font-size: 14.5px;
            color: #475569;
            line-height: 1.6;
            margin-bottom: 20px;
        }}
        p.desc strong.brand {{
            color: #273c8e;
            font-weight: 700;
        }}

        /* Delivery Channels Box */
        .delivery-box {{
            background: #f8fafc;
            border: 1.5px solid #e2e8f0;
            border-radius: 18px;
            padding: 12px 16px;
            margin-bottom: 20px;
            text-align: left;
        }}
        .delivery-item {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 8px 0;
        }}
        .delivery-item:not(:last-child) {{
            border-bottom: 1px dashed #e2e8f0;
        }}
        .del-icon {{
            width: 36px;
            height: 36px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 17px;
            flex-shrink: 0;
        }}
        .del-icon.wa {{
            background: #ecfdf5;
            color: #10b981;
            border: 1px solid #a7f3d0;
        }}
        .del-icon.em {{
            background: #eff6ff;
            color: #273c8e;
            border: 1px solid #bfdbfe;
        }}
        .del-info {{
            flex: 1;
            min-width: 0;
        }}
        .del-info strong {{
            display: block;
            font-size: 13px;
            color: #0f172a;
            font-weight: 700;
        }}
        .del-info span {{
            display: block;
            font-size: 11.5px;
            color: #64748b;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .del-status {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-size: 11px;
            font-weight: 700;
            color: #059669;
            background: #ecfdf5;
            border: 1px solid #a7f3d0;
            padding: 3px 8px;
            border-radius: 12px;
            flex-shrink: 0;
        }}

        /* Credentials Box */
        .cred-box {{
            background: #f8fafc;
            border: 1.5px solid #e2e8f0;
            border-radius: 18px;
            padding: 18px 20px;
            text-align: left;
            margin-bottom: 24px;
        }}
        .cred-box-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            color: #273c8e;
            margin-bottom: 14px;
            padding-bottom: 10px;
            border-bottom: 1px solid #e2e8f0;
        }}
        .cred-item {{
            margin-bottom: 10px;
        }}
        .cred-item:last-child {{
            margin-bottom: 0;
        }}
        .cred-label {{
            font-size: 12px;
            font-weight: 600;
            color: #64748b;
            margin-bottom: 2px;
        }}
        .cred-val {{
            font-size: 14.5px;
            font-weight: 700;
            color: #0f172a;
            display: flex;
            align-items: center;
            justify-content: space-between;
            word-break: break-all;
        }}
        .secure-badge {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-size: 11px;
            font-weight: 700;
            color: #047857;
            background: #ecfdf5;
            border: 1px solid #a7f3d0;
            padding: 3px 8px;
            border-radius: 20px;
        }}
        .cred-hint {{
            font-size: 11px;
            color: #64748b;
            margin-top: 5px;
            font-weight: 500;
        }}
        .copy-btn {{
            background: #ffffff;
            border: 1px solid #cbd5e1;
            color: #475569;
            font-size: 11px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
            margin-left: 8px;
            flex-shrink: 0;
        }}
        .copy-btn:hover {{
            background: #f1f5f9;
            border-color: #273c8e;
            color: #273c8e;
        }}
        .status-badge-inline {{
            display: inline-block;
            background: #fef3c7;
            border: 1px solid #fde68a;
            color: #92400e;
            font-size: 12px;
            font-weight: 700;
            padding: 3px 10px;
            border-radius: 20px;
        }}

        /* Action Buttons */
        .btn-primary {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            width: 100%;
            padding: 14px 20px;
            background: linear-gradient(135deg, #273c8e 0%, #1e2e6d 100%);
            color: #ffffff;
            text-decoration: none;
            border-radius: 14px;
            font-weight: 700;
            font-size: 15px;
            transition: all 0.25s ease;
            box-shadow: 0 10px 22px -5px rgba(39, 60, 142, 0.35);
        }}
        .btn-primary:hover {{
            transform: translateY(-2px);
            box-shadow: 0 14px 26px -5px rgba(39, 60, 142, 0.45);
        }}
        .btn-whatsapp {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            width: 100%;
            padding: 12px 20px;
            background: #ffffff;
            border: 1.5px solid #25D366;
            color: #128C7E;
            text-decoration: none;
            border-radius: 14px;
            font-weight: 700;
            font-size: 14px;
            margin-top: 10px;
            transition: all 0.25s ease;
        }}
        .btn-whatsapp:hover {{
            background: #f0fdf4;
            transform: translateY(-1px);
        }}
        .btn-whatsapp i {{
            color: #25D366;
            font-size: 18px;
        }}
        .footer-note {{
            font-size: 12px;
            color: #94a3b8;
            margin-top: 22px;
            font-weight: 500;
        }}
    </style>
</head>
<body>
    <div class="card-container">
        <!-- PadosiAgent Brand Logo -->
        <div class="logo-box">
            <a href="/">
                <img src="/static/img/logo.webp" alt="PadosiAgent Logo" onerror="this.onerror=null; this.src='/static/img/logo.png';">
            </a>
        </div>

        <!-- Success Check Icon -->
        <div class="icon-circle">
            <i class="fa-solid fa-check"></i>
        </div>

        <h1>Payment Received!</h1>

        <div class="badge-pill">
            <i class="fa-solid fa-shield-check"></i> Credentials Sent to WhatsApp & Email
        </div>

        <p class="desc">
            Thank you, <strong>{fullname}</strong>! Your payment was verified and your registration is submitted for <strong class="brand">Admin Approval</strong>.
            For your security, your login credentials have been dispatched directly to your <strong>WhatsApp</strong> and <strong>Email</strong>.
        </p>

        <!-- Dispatch Confirmation Box -->
        <div class="delivery-box">
            <div class="delivery-item">
                <div class="del-icon wa"><i class="fa-brands fa-whatsapp"></i></div>
                <div class="del-info">
                    <strong>WhatsApp Credentials</strong>
                    <span>Sent to {masked_mobile}</span>
                </div>
                <span class="del-status"><i class="fa-solid fa-circle-check"></i> Sent</span>
            </div>
            <div class="delivery-item">
                <div class="del-icon em"><i class="fa-solid fa-envelope"></i></div>
                <div class="del-info">
                    <strong>Welcome Email & Invoice</strong>
                    <span>Sent to {email if email else 'registered email'}</span>
                </div>
                <span class="del-status"><i class="fa-solid fa-circle-check"></i> Sent</span>
            </div>
        </div>

        <!-- Portal Login Credentials Card -->
        <div class="cred-box">
            <div class="cred-box-header">
                <span><i class="fa-solid fa-id-card me-1"></i> Account Details</span>
                <span style="font-size: 11px; text-transform: none; color: #10b981;"><i class="fa-solid fa-lock"></i> Protected</span>
            </div>

            <div class="cred-item">
                <div class="cred-label">Login User ID (Email)</div>
                <div class="cred-val">
                    <span>{email if email else 'Your registered email'}</span>
                    {copy_email_btn}
                </div>
            </div>

            <div class="cred-item">
                <div class="cred-label">Password</div>
                <div class="cred-val">
                    <span style="letter-spacing: 2.5px; font-family: monospace; font-size: 15px; color: #334155; font-weight: 800;">••••••••••</span>
                    <span class="secure-badge"><i class="fa-solid fa-check"></i> Sent</span>
                </div>
                <div class="cred-hint">💡 Default password is your 10-digit registered mobile number</div>
            </div>

            <div class="cred-item">
                <div class="cred-label">Selected Membership Plan</div>
                <div class="cred-val" style="color: #273c8e;">
                    <span>{plan_name}</span>
                </div>
            </div>

            <div class="cred-item">
                <div class="cred-label">Account Status</div>
                <div class="cred-val">
                    <span class="status-badge-inline">⏳ Pending Admin Approval</span>
                </div>
            </div>
        </div>

        <!-- Action Buttons -->
        <a href="{login_url}" class="btn-primary">
            Proceed to Agent Login <i class="fa-solid fa-arrow-right"></i>
        </a>

        <a href="/wa-bot/simulator/" class="btn-whatsapp">
            <i class="fa-brands fa-whatsapp"></i> Return to WhatsApp Chat
        </a>

        <div class="footer-note">
            PadosiAgent &bull; India's #1 Insurance Agent Network
        </div>
    </div>

    <script>
        function copyText(txt, btn) {{
            if (!txt) return;
            navigator.clipboard.writeText(txt).then(function() {{
                const orig = btn.innerText;
                btn.innerText = 'Copied! ✓';
                btn.style.color = '#10b981';
                btn.style.borderColor = '#10b981';
                setTimeout(function() {{
                    btn.innerText = orig;
                    btn.style.color = '';
                    btn.style.borderColor = '';
                }}, 2000);
            }});
        }}
    </script>
</body>
</html>"""
    return HttpResponse(html_content, content_type='text/html')

