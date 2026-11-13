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
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from .models import WaBotSession, WaBotMessageLog
from .services.state_machine import process_message
from .services.message_sender import mask_phone, send_text_message

from apps.wa_agent_bot.services.site_url import bot_site_url

logger = logging.getLogger(__name__)

# ── Rate limiting ───────────────────────────────────────────────────────
RATE_LIMIT_PER_PHONE = 10  # max messages per minute per phone
RATE_LIMIT_WINDOW = 60  # window in seconds


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
    Verify an incoming webhook via HMAC header or the shared token in the URL.
    Fails closed in production when WA_BOT_WEBHOOK_SECRET is not configured.
    """
    secret = os.environ.get("WA_BOT_WEBHOOK_SECRET", "").strip()
    if not secret:
        if settings.DEBUG:
            from apps.admin_panel.middleware import ThreatMonitorMiddleware
            client_ip = ThreatMonitorMiddleware.get_client_ip(request)
            if client_ip in ("127.0.0.1", "::1", "localhost"):
                return True
        logger.error(
            "[WA-Bot] WA_BOT_WEBHOOK_SECRET not set — rejecting inbound webhook"
        )
        return False

    signature = request.headers.get("X-Webhook-Signature", "")
    if signature:
        expected = hmac.new(
            secret.encode("utf-8"), request.body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

    # OpenWA cannot sign requests; sync_openwa_webhook() registers the URL with ?token=<secret>.
    token = request.GET.get("token", "")
    if token:
        return hmac.compare_digest(token, secret)

    logger.warning("[WA-Bot] Missing webhook signature/token")
    return False


def _extract_message_data(payload):
    """
    Extract phone number and message text from the webhook payload.
    Supports multiple payload formats from OpenWA.

    Returns:
        tuple: (phone_number, message_text, message_type) or (None, None, None) on failure
    """
    # Format 1: Direct event data (from webhook service)
    # { "event": "message:received", "data": { "from": "919876543210@c.us", "body": "hello", ... } }
    data = payload.get("data", payload)

    # Ignore outgoing messages sent by the bot itself (prevent echo loop)
    if data.get("fromMe") is True or (
        isinstance(data.get("id"), dict) and data.get("id", {}).get("fromMe") is True
    ):
        return None, None, None

    # Extract phone number
    phone = None
    for key in ("from", "chatId", "sender", "phone", "phone_number"):
        val = data.get(key)
        if val:
            phone = val
            break

    if not phone:
        # Try nested contact
        contact = data.get("contact", {})
        phone = contact.get("id") or contact.get("phone")

    if not phone:
        return None, None, None

    # Group (@g.us), @lid and broadcast chat ids are not a sender phone number.
    if "@" in str(phone) and not str(phone).endswith(("@c.us", "@s.whatsapp.net")):
        return None, None, None

    # Clean phone number (remove @c.us suffix and non-digits)
    phone = str(phone).replace("@c.us", "").replace("@s.whatsapp.net", "")
    phone = "".join(c for c in phone if c.isdigit())

    # Extract message text
    text = None
    for key in ("body", "text", "message", "content"):
        val = data.get(key)
        if val:
            text = str(val).strip()
            break

    if not text:
        return phone, None, None

    # Extract message type
    msg_type = data.get("type", "text")

    return phone, text, msg_type


MESSAGE_DEDUP_TTL = 24 * 60 * 60  # seconds a provider message id is remembered


def _extract_message_id(payload):
    """Provider message id (OpenWA sends a string or a {'_serialized': ...} dict), or None."""
    data = payload.get("data", payload)
    msg_id = data.get("id") or data.get("messageId") or data.get("message_id")
    if isinstance(msg_id, dict):
        msg_id = msg_id.get("_serialized") or msg_id.get("id")
    return str(msg_id)[:200] if msg_id else None


def is_wa_bot_enabled():
    """
    Check if WhatsApp bot service is enabled.
    Priority:
      1. SiteSetting 'wa_agent_bot_enabled' in DB (configured via Admin Panel)
      2. Environment variable 'WA_BOT_ENABLED' (defaults to 'true')
    """
    try:
        from apps.home.models.site_setting import SiteSetting

        val = SiteSetting.get_value("wa_agent_bot_enabled")
        if val is not None:
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ("true", "1", "yes", "t")
            return bool(val)
    except Exception as e:
        logger.debug(f"[WA-Bot] Could not read SiteSetting: {e}")

    return os.environ.get("WA_BOT_ENABLED", "true").lower() in ("true", "1", "yes", "t")


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
        return JsonResponse(
            {"status": "disabled", "message": "WhatsApp Bot is paused via Admin Panel"},
            status=200,
        )

    # ── Verify webhook signature ────────────────────────────────────
    if not _verify_webhook_signature(request):
        logger.warning("[WA-Bot] Invalid webhook signature — rejecting request")
        return JsonResponse({"error": "Invalid signature"}, status=403)

    # ── Parse payload ───────────────────────────────────────────────
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Check event type — only process incoming messages
    event = payload.get("event", "")
    if event and event not in (
        "message.received",
        "message:received",
        "message",
        "chat",
    ):
        # Not a message event — acknowledge and ignore
        return JsonResponse(
            {"status": "ignored", "reason": f"event type: {event}"}, status=200
        )

    # ── Extract message data ────────────────────────────────────────
    phone, text, msg_type = _extract_message_data(payload)

    if not phone:
        logger.debug("[WA-Bot] Could not extract phone number from payload")
        return JsonResponse({"error": "Missing phone number"}, status=400)

    if not text:
        # Non-text message (image, audio, etc.) — politely ignore
        logger.debug(f"[WA-Bot] Non-text message from {mask_phone(phone)} (type={msg_type})")
        return JsonResponse(
            {"status": "ignored", "reason": "non-text message"}, status=200
        )

    # ── Dedup provider redeliveries (would advance the state machine twice) ──
    msg_id = _extract_message_id(payload)
    if msg_id and not cache.add(f"wa_bot_msg_{msg_id}", 1, timeout=MESSAGE_DEDUP_TTL):
        logger.info(
            f"[WA-Bot] Duplicate delivery of message {msg_id} from {mask_phone(phone)} — ignored"
        )
        return JsonResponse({"status": "ignored", "reason": "duplicate"}, status=200)

    # ── Rate limiting ───────────────────────────────────────────────
    if not _check_rate_limit(phone):
        logger.warning(f"[WA-Bot] Rate limit exceeded for {mask_phone(phone)}")
        send_text_message(
            phone,
            "⚠️ You're sending messages too quickly. Please wait a moment and try again.",
            category="rate_limit",
        )
        return JsonResponse({"status": "rate_limited"}, status=429)

    # ── Get or create session ───────────────────────────────────────
    session, created = WaBotSession.objects.get_or_create(
        phone_number=phone,
        defaults={
            "state": WaBotSession.STATE_WELCOME,
            "registration_data": {},
            "session_context": {},
        },
    )

    if created:
        logger.info(f"[WA-Bot] New session created for {mask_phone(phone)}")

    # Hold the row lock while processing: a Razorpay activation committing meanwhile would otherwise
    # be overwritten by this stale copy (audit WA7). The reply is sent after commit, outside the lock.
    with transaction.atomic():
        session = WaBotSession.objects.select_for_update().get(pk=session.pk)

        # ── Update activity tracking ────────────────────────────────────
        session.update_last_activity()

        # ── Log incoming message ────────────────────────────────────────
        WaBotMessageLog.objects.create(
            session=session,
            phone_number=phone[:20],
            direction=WaBotMessageLog.DIRECTION_IN,
            status=WaBotMessageLog.STATUS_RECEIVED,
            content=text[:2000],  # cap at 2000 chars
            state_at_time=session.state,
        )

        # ── Process through state machine ───────────────────────────────
        try:
            with transaction.atomic():  # savepoint: a DB error here can't break the outer transaction
                reply = process_message(session, text)
        except Exception as e:
            logger.error(
                f"[WA-Bot] Error processing message from {mask_phone(phone)}: {e}", exc_info=True
            )
            reply = (
                "😔 Sorry, something went wrong on our end.\n"
                "Please try again in a moment or type *restart* to start over."
            )

        # ── Save session (state machine already saved, but ensure) ──────
        session.save()

    # ── Send reply via OpenWA (send_text_message logs it) ───────────
    send_result = send_text_message(phone, reply, session=session)

    if not send_result["success"]:
        logger.error(
            f"[WA-Bot] Failed to send reply to {mask_phone(phone)}: {send_result.get('error', 'unknown')}"
        )

    return JsonResponse(
        {
            "status": "processed",
            "phone": phone,
            "state": session.state,
            "message_sent": send_result["success"],
        }
    )


@require_GET
def bot_health(request):
    """
    Health check endpoint for the WhatsApp bot.
    GET /wa-bot/health/
    Restricted to authenticated admin sessions and internal/localhost monitoring.
    """
    from apps.admin_panel.auth import _get_admin_from_session
    from apps.admin_panel.middleware import ThreatMonitorMiddleware

    client_ip = ThreatMonitorMiddleware.get_client_ip(request)
    is_admin = bool(_get_admin_from_session(request))
    is_internal = client_ip in ("127.0.0.1", "::1", "localhost")

    if not is_admin and not is_internal:
        return JsonResponse({"status": "unauthorized"}, status=401)

    enabled = is_wa_bot_enabled()
    total_sessions = WaBotSession.objects.count()
    registered_sessions = WaBotSession.objects.filter(is_registered=True).count()

    return JsonResponse(
        {
            "status": "healthy",
            "enabled": enabled,
            "total_sessions": total_sessions,
            "registered_agents": registered_sessions,
        }
    )


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
    from apps.agents.services.razorpay_checkout import (
        ensure_payment_captured,
        razorpay_client,
        razorpay_webhook_secret,
    )
    from apps.agents.views.registration import (
        _expected_amount_paise,
        _paise_amounts_match,
    )
    from .services.payment_service import activate_agent_subscription_after_payment

    raw_body = request.body.decode("utf-8")
    signature = request.headers.get("X-Razorpay-Signature", "")
    secret = razorpay_webhook_secret()

    if not secret or not signature:
        logger.error(
            "[WA-Bot-Razorpay] Webhook rejected: secret not configured or signature missing"
        )
        return JsonResponse(
            {"status": "error", "message": "Invalid signature"}, status=400
        )
    expected = hmac.new(
        secret.encode("utf-8"), request.body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        logger.error("[WA-Bot-Razorpay] Webhook signature verification failed")
        return JsonResponse(
            {"status": "error", "message": "Invalid signature"}, status=400
        )

    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)

    # ── Replay protection: reject stale events (older than 5 minutes) ────────
    import time as _time_mod
    event_created_at = data.get("created_at")
    if event_created_at:
        try:
            age_seconds = abs(_time_mod.time() - float(event_created_at))
            if age_seconds > 300:  # 5 minutes
                logger.warning(
                    "[WA-Bot-Razorpay] Stale webhook rejected (age=%.0fs, event=%s)",
                    age_seconds,
                    data.get("event", "?"),
                )
                return JsonResponse({"status": "ignored", "message": "Stale event"})
        except (TypeError, ValueError):
            pass

    # ── Idempotency guard: reject duplicate event IDs ────────────────────────
    rzp_event_id = request.headers.get("X-Razorpay-Event-Id", "").strip() or data.get("event_id", "")
    if rzp_event_id:
        from django.core.cache import cache as _cache_mod
        _idem_key = f"rzp_event_{rzp_event_id}"
        if _cache_mod.get(_idem_key):
            logger.info("[WA-Bot-Razorpay] Duplicate webhook event ignored: %s", rzp_event_id)
            return JsonResponse({"status": "ignored", "message": "Already processed"})

    event = data.get("event", "")
    logger.info(f"[WA-Bot-Razorpay] Webhook event received: {event}")

    # Signed expired/cancelled/refund events also carry the notes: only paid events may activate.
    if event not in ("payment_link.paid", "order.paid", "payment.captured"):
        return JsonResponse({"status": "ignored", "message": f"event type: {event}"})

    # Extract payment / link details
    payload = data.get("payload") or {}
    plink_entity = (payload.get("payment_link") or {}).get("entity") or {}
    payment_entity = (payload.get("payment") or {}).get("entity") or {}
    order_entity = (payload.get("order") or {}).get("entity") or {}

    notes = (
        plink_entity.get("notes")
        or payment_entity.get("notes")
        or order_entity.get("notes")
        or {}
    )
    subscription_id = notes.get("subscription_id")
    payment_id = payment_entity.get("id") or plink_entity.get("id") or order_entity.get("id")

    sub = None
    if subscription_id:
        sub = AgentSubscription.objects.filter(pk=subscription_id).first()

    if not sub:
        # Try matching by payment link ID or order ID
        link_id = plink_entity.get("id") or order_entity.get("id")
        if link_id:
            sub = AgentSubscription.objects.filter(razorpay_order_id=link_id).first()

    if sub:
        if sub.payment_status == "completed":
            return JsonResponse({"status": "success", "message": "Already activated"})

        # Invariant 10: only a captured payment is money (an 'authorized' one is captured first).
        if payment_entity:
            captured = ensure_payment_captured(razorpay_client(), payment_entity)
            if not captured:
                logger.error(
                    f"[WA-Bot-Razorpay] Payment {payment_id} for sub #{sub.id} not captured "
                    f"(event {event}) — not activating"
                )
                return JsonResponse(
                    {"status": "ignored", "message": "Payment not captured"}
                )

            expected_paise = _expected_amount_paise(sub.registration_amount)
            if not _paise_amounts_match(captured.get("amount"), expected_paise):
                # 200 so Razorpay does not retry a payment that will never match.
                logger.error(
                    f"[WA-Bot-Razorpay] Amount mismatch for sub #{sub.id}: payment {payment_id} "
                    f"paid {captured.get('amount')} paise, expected {expected_paise} paise — not activating"
                )
                return JsonResponse({"status": "ignored", "message": "Amount mismatch"})

        success, msg = activate_agent_subscription_after_payment(
            sub.id, payment_id=payment_id, signature=signature
        )
        logger.info(f"[WA-Bot-Razorpay] Activation result for sub #{sub.id}: {msg}")
        if success and rzp_event_id:
            # Mark only after success so a failed activation stays retryable.
            _cache_mod.set(_idem_key, 1, timeout=86400)
        return JsonResponse({"status": "success", "message": msg})
    else:
        logger.warning(
            f"[WA-Bot-Razorpay] Could not match subscription for event {event}"
        )
        return JsonResponse({"status": "ignored", "message": "Subscription not found"})


@require_GET
def payment_callback(request):
    """
    Payment Link return callback URL.
    GET /wa-bot/payment-callback/?razorpay_payment_id=...&razorpay_payment_link_id=...&razorpay_payment_link_status=paid
    """
    from apps.agents.models import AgentSubscription
    from .services.payment_service import activate_agent_subscription_after_payment

    payment_id = request.GET.get("razorpay_payment_id", "")
    link_id = request.GET.get("razorpay_payment_link_id", "")
    signature = request.GET.get("razorpay_signature", "")

    site_url = bot_site_url()
    login_url = f"{site_url}/agent-login/"

    sub = None
    if link_id:
        sub = AgentSubscription.objects.filter(razorpay_order_id=link_id).first()
    if not sub and payment_id:
        sub = AgentSubscription.objects.filter(razorpay_payment_id=payment_id).first()

    if sub:
        # Security verification: Verify payment validity before activation
        is_verified = False
        if sub.payment_status == "completed":
            is_verified = True
        else:
            from apps.agents.services.razorpay_checkout import razorpay_client

            client = razorpay_client()
            # Query params prove nothing: ask Razorpay whether this subscription's own link was paid.
            if client and link_id and link_id == sub.razorpay_order_id:
                try:
                    from .services.payment_service import payment_link_paid_in_full

                    plink = client.payment_link.fetch(link_id)
                    is_verified = payment_link_paid_in_full(plink, sub)
                    if not is_verified:
                        logger.warning(
                            f"[WA-Bot-Security] Payment link {link_id} not paid: {(plink or {}).get('status')}"
                        )
                except Exception as e:
                    logger.error(
                        f"[WA-Bot-Security] Razorpay verification error for {link_id}: {e}"
                    )

        if is_verified:
            activate_agent_subscription_after_payment(
                sub.id, payment_id=payment_id, signature=signature
            )
            sub.refresh_from_db()
        else:
            logger.warning(
                f"[WA-Bot-Security] Rejected unverified activation attempt for sub #{sub.id}"
            )

    # Anyone can open this URL with a link id, so only reveal account details once payment is confirmed.
    agent = sub.agent if sub and sub.payment_status == "completed" else None
    raw_email = agent.email if agent and agent.email else ""
    mobile_clean = (
        "".join(c for c in (agent.mobile or "") if c.isdigit()) if agent else ""
    )
    masked_mobile = (
        f"+91 {mobile_clean[:2]}•••••{mobile_clean[-3:]}"
        if len(mobile_clean) == 10
        else (f"+{mobile_clean}" if mobile_clean else "Registered Number")
    )
    # No request passed: the old page ran no context processors (they query the DB).
    html_content = render_to_string(
        "wa_agent_bot/payment_callback.html",
        {
            "fullname": agent.fullname if agent and agent.fullname else "Agent",
            "email": raw_email,
            "email_json": json.dumps(raw_email),
            "masked_mobile": masked_mobile,
            "plan_name": sub.selected_plan if sub and sub.selected_plan else "Membership Plan",
            "login_url": login_url,
        },
    )
    return HttpResponse(html_content, content_type="text/html")
