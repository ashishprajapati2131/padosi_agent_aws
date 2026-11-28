"""
Short, admin-visible trace of what happened to each WhatsApp webhook (Hub → Live diagnostics).

Kept in the shared cache (no table): the last TRACE_SIZE message webhooks with their outcome and a
plain-language reason, plus when OpenWA last delivered anything at all. Phones are masked.
"""

import datetime
import logging
import time

from django.core.cache import cache

from .message_sender import mask_phone

logger = logging.getLogger(__name__)

TRACE_KEY = "wa_bot_webhook_trace"
LAST_SEEN_KEY = "wa_bot_webhook_last_seen"
TRACE_SIZE = 30
TTL = 7 * 24 * 3600

PROCESSED = "processed"
IGNORED = "ignored"
REJECTED = "rejected"
FAILED = "reply_failed"


def _now():
    return datetime.datetime.now().strftime("%d %b %H:%M:%S")


def seen(event):
    """Any request that reached the webhook, message or not."""
    try:
        cache.set(
            LAST_SEEN_KEY,
            {"at": _now(), "ts": time.time(), "event": str(event or "")[:40]},
            timeout=TTL,
        )
    except Exception as e:  # diagnostics must never break message handling
        logger.warning(f"[WA-Bot] webhook trace unavailable: {e}")


def record(outcome, detail, phone="", text=""):
    try:
        events = cache.get(TRACE_KEY) or []
        events.insert(
            0,
            {
                "at": _now(),
                "outcome": outcome,
                "detail": str(detail)[:200],
                "phone": mask_phone(phone) if phone else "",
                "text": str(text or "")[:30],
            },
        )
        cache.set(TRACE_KEY, events[:TRACE_SIZE], timeout=TTL)
    except Exception as e:
        logger.warning(f"[WA-Bot] webhook trace unavailable: {e}")


def recent():
    return cache.get(TRACE_KEY) or []


def last_seen():
    return cache.get(LAST_SEEN_KEY)
