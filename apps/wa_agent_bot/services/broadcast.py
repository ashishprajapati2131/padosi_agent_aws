"""
WhatsApp broadcast: one message to many numbers (selected agents and/or an uploaded sheet).

The admin page (Admin → WhatsApp → Broadcast) saves a WaBroadcast with its recipients;
the 'wa-broadcast' background job (apps/agents/services/background_jobs.py) sends them at
the chosen pace. If WhatsApp disconnects or sends keep failing, the broadcast pauses, the
admin gets an email, and it resumes by itself once WhatsApp works again.
The `wa_broadcast_active_agents` command uses run_broadcast() to send straight away.
A number that already got this exact text is always skipped.
"""

import csv
import io
import logging
import random
import time
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils.html import escape

from apps.agents.services.og_urls import CANONICAL_PADOSI_ORIGIN
from apps.wa_agent_bot.models import WaBotMessageLog
from apps.wa_agent_bot.services.message_sender import CAPTION_MAX, send_image_message, send_text_message

logger = logging.getLogger(__name__)

CATEGORY = "broadcast"
TICK_SECONDS = 50  # one background-job run; the job is claimed every 60 s
BLOCK_RECHECK = timedelta(minutes=15)  # how often a paused broadcast checks WhatsApp again
FAIL_STREAK_LIMIT = 5  # sends failing in a row while "connected" = treat as blocked
FAIL_RETRY = timedelta(hours=1)  # then retry one send every hour
MAX_SHEET_ROWS = 5000
MAX_SHEET_BYTES = 2 * 1024 * 1024
PHONE_HEADERS = ("mobile", "phone", "whatsapp", "number", "contact")


def phone10(raw):
    """Last 10 digits of an Indian mobile, or '' when it is not a valid one."""
    s = str(raw or "").strip()
    if s.endswith(".0"):
        s = s[:-2]  # Excel numbers read as floats: 9876543210.0
    digits = "".join(c for c in s if c.isdigit())[-10:]
    return digits if len(digits) == 10 and digits[0] in "6789" else ""


def site_base():
    return (getattr(settings, "APP_URL", "") or CANONICAL_PADOSI_ORIGIN).rstrip("/")


def profile_link(agent, base=None):
    return f"{(base or site_base()).rstrip('/')}/{agent.state_code}/{agent.agent_slug}/"


def card_image_url(agent, base=None):
    """The agent's share card (same image as the profile's og:image), served at /og-image/<id>/preview.jpg."""
    from django.urls import reverse
    from apps.agents.models import OG_IMAGE_CACHE_VERSION
    from apps.agents.services.og_image import card_version

    path = reverse("agents:agent_og_image", kwargs={"agent_id": agent.id})
    return f"{(base or site_base()).rstrip('/')}{path}?v={OG_IMAGE_CACHE_VERSION}-{card_version(agent)}"


def render_text(message, name="", link=""):
    """
    {name} -> the person's name; {link} -> their profile link, added at the end when the text has no {link}.
    Without a link, a line holding {link} is left out (same rule as the WhatsApp message templates).
    """
    text = message.strip().replace("{name}", (name or "").strip() or "there")
    if "{link}" in text:
        if link:
            return text.replace("{link}", link).strip()
        return "\n".join(line for line in text.split("\n") if "{link}" not in line).strip()
    return f"{text}\n\nYour profile: {link}" if link else text


# ── Saved (pre-drafted) messages, kept in SiteSetting ────────────────────────
TEMPLATES_KEY = "wa_broadcast_templates"
MAX_TEMPLATES = 50
DEFAULT_TEMPLATES = [
    {
        "name": "Diwali 2026",
        "text": (
            "Happy Diwali from all of us at PadosiAgent.\n\n"
            "Our 500+ agents across 15+ cities are lighting diyas in their own neighbourhoods tonight, "
            "the same streets they serve every day.\n\n"
            "From our neighbourhood to yours, have a safe and bright Diwali.\n\n"
            "#HappyDiwali #PadosiWaliDiwali #PadosiAgent #Diwali2026\n\n"
            "Your profile: {link}"
        ),
    },
]


def get_templates():
    from apps.home.models.site_setting import SiteSetting

    saved = SiteSetting.get_value(TEMPLATES_KEY)
    if isinstance(saved, list):
        return [t for t in saved if isinstance(t, dict) and t.get("name") and t.get("text")]
    return [dict(t) for t in DEFAULT_TEMPLATES]


def save_template(name, text, max_len=4000):
    """Add or replace a saved message by name. Raises ValueError on bad input."""
    from apps.home.models.site_setting import SiteSetting

    name, text = (name or "").strip()[:60], (text or "").strip()
    if not name or not text:
        raise ValueError("Give the message a name and some text.")
    if len(text) > max_len:
        raise ValueError(f"Message is longer than {max_len} characters.")
    items = [t for t in get_templates() if t["name"] != name]
    if len(items) >= MAX_TEMPLATES:
        raise ValueError(f"You can keep up to {MAX_TEMPLATES} saved messages. Delete one first.")
    items.append({"name": name, "text": text})
    SiteSetting.set_value(TEMPLATES_KEY, items, group="whatsapp")
    return items


def delete_template(name):
    from apps.home.models.site_setting import SiteSetting

    items = [t for t in get_templates() if t["name"] != (name or "").strip()]
    SiteSetting.set_value(TEMPLATES_KEY, items, group="whatsapp")
    return items


def _rows_from_upload(upload):
    name = (upload.name or "").lower()
    data = upload.read(MAX_SHEET_BYTES + 1)
    if len(data) > MAX_SHEET_BYTES:
        raise ValueError("Sheet is larger than 2 MB.")
    if name.endswith(".csv"):
        text = data.decode("utf-8-sig", errors="replace")
        return list(csv.reader(io.StringIO(text)))
    if name.endswith(".xlsx"):
        from openpyxl import load_workbook

        try:
            ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        except Exception:
            raise ValueError("Could not read the Excel file.")
        return [
            ["" if v is None else str(v) for v in row]
            for row in ws.iter_rows(values_only=True)
        ]
    raise ValueError("Upload a .csv or .xlsx file.")


def parse_sheet(upload):
    """
    Return [(name, phone10), ...] from a CSV/XLSX upload.
    Uses a column whose header mentions mobile/phone/whatsapp/number; without a header,
    the first column that holds phone numbers. A 'name' column is optional.
    """
    rows = [r for r in _rows_from_upload(upload) if any(str(c).strip() for c in r)]
    if not rows:
        raise ValueError("The sheet is empty.")
    if len(rows) > MAX_SHEET_ROWS + 1:
        raise ValueError(f"The sheet has more than {MAX_SHEET_ROWS} rows.")

    header = [str(c).strip().lower() for c in rows[0]]
    phone_col = next(
        (i for i, h in enumerate(header) if any(k in h for k in PHONE_HEADERS)), None
    )
    name_col = next((i for i, h in enumerate(header) if "name" in h), None)
    if phone_col is not None:
        body = rows[1:]
    else:
        body = rows
        name_col = None
        phone_col = next(
            (
                i
                for i in range(max(len(r) for r in rows))
                if any(phone10(r[i]) for r in rows if i < len(r))
            ),
            None,
        )
        if phone_col is None:
            raise ValueError(
                'No mobile number column found. Add a header named "mobile".'
            )

    out = []
    for r in body:
        phone = phone10(r[phone_col]) if phone_col < len(r) else ""
        if phone:
            name = (
                str(r[name_col]).strip()
                if name_col is not None and name_col < len(r)
                else ""
            )
            out.append((name, phone))
    return out


def build_recipients(agents=(), sheet_rows=(), add_link=True, base=None):
    """
    Merge agents and sheet rows into [{'phone', 'name', 'link'}], one per number.
    A sheet number that belongs to an active agent or event participant also gets that agent's profile link and card.
    """
    from django.db.models import Q
    from apps.agents.models import Agent

    base = base or site_base()
    seen, out = set(), []

    def _is_card_eligible(agent):
        if not agent:
            return False
        # Active agents, event trial/challenge agents, and event participants get their card & profile link
        if getattr(agent, "status", "") in ("active", "event_challenge"):
            return True
        try:
            if hasattr(agent, "event_referral_participant") and agent.event_referral_participant is not None:
                return True
        except Exception:
            pass
        return False

    def add(phone, name, agent):
        if agent is not None and not _is_card_eligible(agent):
            agent = None  # profile is not public until approval: send no link or card
        if phone and phone not in seen:
            seen.add(phone)
            out.append(
                {
                    "phone": phone,
                    "name": name,
                    "link": profile_link(agent, base) if (agent and add_link) else "",
                    "image": card_image_url(agent, base) if (agent and add_link) else "",
                }
            )

    for a in agents:
        add(phone10(a.mobile), a.fullname, a)

    sheet_rows = list(sheet_rows)
    if sheet_rows:
        by_phone = {}
        if add_link:
            for a in Agent.objects.filter(
                Q(status__in=["active", "event_challenge"]) | Q(event_referral_participant__isnull=False)
            ).select_related("profile"):
                by_phone.setdefault(phone10(a.mobile), a)
        for name, phone in sheet_rows:
            agent = by_phone.get(phone)
            add(phone, name or (agent.fullname if agent else ""), agent)
    return out


def already_sent(phone, text, since=None):
    """Did this number get exactly this text? since= limits it to one broadcast's lifetime, so a new
    broadcast reaches everyone again but a restart mid-broadcast never sends twice."""
    qs = WaBotMessageLog.objects.filter(
        phone_number__endswith=phone,
        category=CATEGORY,
        status=WaBotMessageLog.STATUS_SENT,
        content=text[:5000],
    )
    if since is not None:
        qs = qs.filter(created_at__gte=since)
    return qs.exists()


def new_stats(total):
    return {"total": total, "sent": 0, "failed": 0, "skipped": 0, "errors": []}


def run_broadcast(
    recipients,
    message,
    min_delay=6,
    max_delay=12,
    on_progress=None,
    should_stop=None,
    stats=None,
):
    """Send to every recipient, skipping ones already sent this text. Returns the counts."""
    stats = stats if stats is not None else new_stats(len(recipients))
    for i, r in enumerate(recipients, 1):
        if should_stop and should_stop():
            stats["cancelled"] = True
            break
        text = render_text(message, r["name"], r["link"])
        if already_sent(r["phone"], text):
            stats["skipped"] += 1
        else:
            result = send_text_message(r["phone"], text, category=CATEGORY)
            if result.get("success"):
                stats["sent"] += 1
            else:
                stats["failed"] += 1
                stats["errors"] = (
                    stats["errors"] + [f"{r['phone']}: {result.get('error')}"]
                )[-20:]
            if i < len(recipients):
                time.sleep(random.uniform(min_delay, max_delay))
        if on_progress:
            on_progress(stats)
    return stats
# ── Saved broadcasts, sent by the 'wa-broadcast' background job ─────────────


def _models():
    from apps.wa_agent_bot.models import WaBroadcast, WaBroadcastRecipient

    return WaBroadcast, WaBroadcastRecipient


def create_broadcast(
    recipients,
    message,
    *,
    add_link=True,
    send_card=True,
    rate_count=49,
    rate_hours=4,
    min_gap_seconds=60,
    alert_email="",
    created_by="",
):
    WaBroadcast, WaBroadcastRecipient = _models()
    with transaction.atomic():
        b = WaBroadcast.objects.create(
            message=message,
            add_link=add_link,
            send_card=send_card,
            rate_count=rate_count,
            rate_hours=rate_hours,
            min_gap_seconds=min_gap_seconds,
            alert_email=alert_email,
            created_by=created_by,
            next_send_at=datetime.now(),
        )
        WaBroadcastRecipient.objects.bulk_create(
            [
                WaBroadcastRecipient(
                    broadcast=b,
                    phone=r["phone"],
                    name=r["name"][:255],
                    link=r["link"][:500],
                    image_url=r.get("image", "")[:500],
                )
                for r in recipients
            ],
            batch_size=500,
        )
    return b


def cancel_broadcast(broadcast_id):
    WaBroadcast, _ = _models()
    return WaBroadcast.objects.filter(
        pk=broadcast_id,
        status__in=[WaBroadcast.STATUS_RUNNING, WaBroadcast.STATUS_BLOCKED],
    ).update(status=WaBroadcast.STATUS_CANCELLED, finished_at=datetime.now())


def resume_now(broadcast_id):
    """Admin says WhatsApp is fine again: try the next message on the next job run."""
    WaBroadcast, _ = _models()
    return WaBroadcast.objects.filter(
        pk=broadcast_id, status=WaBroadcast.STATUS_BLOCKED
    ).update(
        status=WaBroadcast.STATUS_RUNNING,
        next_send_at=datetime.now(),
        next_check_at=None,
        fail_streak=0,
    )


def _jitter(gap, floor):
    """Uneven gaps look less like a bot; never below the admin's minimum delay."""
    return max(floor, gap * random.uniform(0.85, 1.15))


def _whatsapp_ok():
    from apps.wa_agent_bot.services.openwa_admin_service import (
        get_openwa_session_status,
    )

    try:
        st = get_openwa_session_status()
    except Exception as e:
        return False, f"WhatsApp status check failed: {e}"
    if st.get("is_connected"):
        return True, ""
    return False, st.get(
        "error"
    ) or f"WhatsApp is not connected (status: {st.get('status')})"


def _alert(b, subject, lines):
    from apps.agents.services.brevo import send_brevo_email

    to = b.alert_email or getattr(settings, "SECURITY_ALERT_EMAIL", "") or ""
    if not to:
        logger.warning(
            "[WA-Broadcast] no alert email for broadcast %s: %s", b.pk, subject
        )
        return
    c = counts(b)
    html = (
        f"<p>{'<br>'.join(escape(line) for line in lines)}</p>"
        f"<p>Broadcast #{b.pk}: sent {c['sent']}, pending {c['pending']}, failed {c['failed']}, "
        f"skipped {c['skipped']} of {c['total']}.</p>"
        f"<p>Message: <i>{escape(b.message[:200])}</i></p>"
        f"<p>Admin &rarr; WhatsApp &rarr; Broadcast</p>"
    )
    try:
        send_brevo_email(to, "PadosiAgent Admin", subject, html)
    except Exception:
        logger.exception("[WA-Broadcast] alert email failed for broadcast %s", b.pk)


def _block(b, reason, recheck):
    WaBroadcast, _ = _models()
    now = datetime.now()
    first_alert = not b.alert_sent
    b.status = WaBroadcast.STATUS_BLOCKED
    b.blocked_at = b.blocked_at or now
    b.next_check_at = now + recheck
    b.last_error = reason[:500]
    b.alert_sent = True
    b.save(
        update_fields=[
            "status",
            "blocked_at",
            "next_check_at",
            "last_error",
            "alert_sent",
        ]
    )
    logger.warning("[WA-Broadcast] #%s paused: %s", b.pk, reason)
    if first_alert:
        _alert(
            b,
            "WhatsApp broadcast paused - account blocked or disconnected",
            [
                "Your WhatsApp broadcast has been paused because WhatsApp stopped accepting messages.",
                f"Reason: {reason}",
                f"It checks WhatsApp again every {int(recheck.total_seconds() // 60)} minutes and resumes "
                "by itself as soon as it works (for example when a 24-hour ban ends).",
                "If the number was logged out, scan the QR code again in Admin > WhatsApp.",
            ],
        )


def _deliver(b, r, text):
    """The agent's card as a photo with the text as caption (always shows, unlike link previews); else plain text."""
    if b.send_card and r.image_url and len(text) <= CAPTION_MAX:
        result = send_image_message(r.phone, r.image_url, text, category=CATEGORY)
        if result.get("success"):
            return result
        # e.g. an OpenWA without send-image: the text still goes out, with its link
        logger.warning("[WA-Broadcast] card photo failed for %s (%s); sending text", r.phone, result.get("error"))
    return send_text_message(r.phone, text, category=CATEGORY)


def _send_next(b):
    WaBroadcast, WaBroadcastRecipient = _models()
    now = datetime.now()
    r = (
        b.recipients.filter(status=WaBroadcastRecipient.STATUS_PENDING)
        .order_by("id")
        .first()
    )
    if r is None:
        b.status, b.finished_at = WaBroadcast.STATUS_DONE, now
        b.save(update_fields=["status", "finished_at"])
        return

    text = render_text(b.message, r.name, r.link)
    if already_sent(r.phone, text, since=b.created_at):
        r.status = WaBroadcastRecipient.STATUS_SKIPPED
        r.save(update_fields=["status"])
        return

    result = _deliver(b, r, text)
    gap = timedelta(seconds=_jitter(b.gap_seconds, b.min_gap_seconds))
    if result.get("success"):
        r.status, r.sent_at = WaBroadcastRecipient.STATUS_SENT, now
        r.save(update_fields=["status", "sent_at"])
        b.fail_streak, b.alert_sent, b.blocked_at, b.next_send_at = (
            0,
            False,
            None,
            now + gap,
        )
        b.save(
            update_fields=["fail_streak", "alert_sent", "blocked_at", "next_send_at"]
        )
        return

    error = (result.get("error") or "Unknown error")[:500]
    ok, reason = _whatsapp_ok()
    if not ok:  # account down: keep this number pending and pause
        _block(b, f"{reason} (last error: {error})", BLOCK_RECHECK)
        return
    r.status, r.error = WaBroadcastRecipient.STATUS_FAILED, error
    r.save(update_fields=["status", "error"])
    b.fail_streak += 1
    b.last_error, b.next_send_at = error, now + gap
    b.save(update_fields=["fail_streak", "last_error", "next_send_at"])
    if b.fail_streak >= FAIL_STREAK_LIMIT:
        _block(
            b,
            f"{b.fail_streak} messages in a row failed. Last error: {error}",
            FAIL_RETRY,
        )


SEND_LOCK = "wa-broadcast:sending"
HEARTBEAT_KEY = "wa-broadcast:last-run"


def process_broadcasts(max_seconds=TICK_SECONDS, sleep=time.sleep, source="job"):
    """
    Send what is due (oldest broadcast first) for up to max_seconds.
    Called by the 'wa-broadcast' background job and by the open Broadcast page (source="page"),
    so messages still go out where background jobs do not run. The lock keeps the two from
    sending the same message twice. Returns False when another run holds the lock.
    """
    from django.core.cache import cache
    from apps.agents.services.background_jobs import _claim

    cache.set(HEARTBEAT_KEY, {"at": datetime.now().isoformat(), "source": source}, None)
    if not _claim(SEND_LOCK, 1, timeout=int(max_seconds) + 60):
        return False
    try:
        _process(max_seconds, sleep)
    finally:
        cache.delete(SEND_LOCK)
    return True


def sender_status():
    """For the page: are background jobs on here, and when did a sender last run?"""
    from django.core.cache import cache
    from apps.agents.services.background_jobs import jobs_enabled

    beat = cache.get(HEARTBEAT_KEY) or {}
    try:
        ago = int((datetime.now() - datetime.fromisoformat(beat["at"])).total_seconds())
    except (KeyError, TypeError, ValueError):
        ago = None
    return {"jobs_enabled": jobs_enabled(), "last_run_ago": ago, "last_source": beat.get("source", "")}


def _process(max_seconds, sleep):
    WaBroadcast, _ = _models()
    deadline = time.monotonic() + max_seconds
    while time.monotonic() < deadline:
        b = (
            WaBroadcast.objects.filter(
                status__in=[WaBroadcast.STATUS_RUNNING, WaBroadcast.STATUS_BLOCKED]
            )
            .order_by("id")
            .first()
        )
        if b is None:
            return
        now = datetime.now()
        if b.status == WaBroadcast.STATUS_BLOCKED:
            if b.next_check_at and b.next_check_at > now:
                return
            ok, reason = _whatsapp_ok()
            if not ok:
                b.next_check_at, b.last_error = now + BLOCK_RECHECK, reason[:500]
                b.save(update_fields=["next_check_at", "last_error"])
                return
            b.status, b.next_send_at, b.next_check_at = (
                WaBroadcast.STATUS_RUNNING,
                now,
                None,
            )
            b.save(update_fields=["status", "next_send_at", "next_check_at"])
            logger.info("[WA-Broadcast] #%s resumed: WhatsApp is connected again", b.pk)
            continue
        if b.next_send_at and b.next_send_at > now:
            wait = (b.next_send_at - now).total_seconds()
            if time.monotonic() + wait >= deadline:
                return
            sleep(wait)
            continue
        _send_next(b)


def counts(b):
    from django.db.models import Count

    c = {"pending": 0, "sent": 0, "failed": 0, "skipped": 0}
    for row in b.recipients.values("status").annotate(n=Count("id")):
        c[row["status"]] = row["n"]
    c["total"] = sum(c.values())
    c["done"] = c["total"] - c["pending"]
    c["percent"] = round(c["done"] * 100 / c["total"]) if c["total"] else 0
    c["eta_hours"] = round(c["pending"] * b.gap_seconds / 3600, 1)
    return c
