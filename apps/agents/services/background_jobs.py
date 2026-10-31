"""Scheduled jobs without cron, for shared hosting.

cPanel cron did not run reliably on this host (and was reverted in
236fd60), and a forever-looping thread dies whenever Passenger recycles or
idles the app process. So jobs are triggered by traffic instead:
BackgroundJobsMiddleware calls maybe_run_due_jobs() after each response. A
job whose interval has passed is claimed with cache.add (Redis or the file
cache, shared by every app process; on MySQL the claim is serialized with
GET_LOCK, see _claim) and runs once in a daemon thread. If the
thread dies, the claim simply expires and the next request after the
interval runs it again; every job is safe to re-run.

On only when settings.BACKGROUND_JOBS_ENABLED (default: on when DEBUG is
off) and never during tests. Audit 2026-10-01 F-21 / F-39.
"""

import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from io import StringIO

from django.conf import settings
from django.core.cache import cache
from django.db import close_old_connections

logger = logging.getLogger(__name__)

# Automatic retries per subscription, so a permanently failing invoice does
# not resend the welcome email every hour.
AUTO_MAX_ATTEMPTS = 3


@contextmanager
def _mysql_named_lock(name):
    """Yield True when this process holds MySQL GET_LOCK(name); always True elsewhere.

    Same approach as the step-1 draft lock in apps/agents/views/registration.py.
    """
    from django.db import connection

    if connection.vendor != "mysql":
        yield True
        return
    lock_name = f"padosi:{name}"[:64]  # MySQL lock names are capped at 64 chars
    has_lock = False
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT GET_LOCK(%s, 0)", [lock_name])
            res = cur.fetchone()
            has_lock = bool(res and res[0] == 1)
    except Exception:
        has_lock = False
    try:
        yield has_lock
    finally:
        if has_lock:
            try:
                with connection.cursor() as cur:
                    cur.execute("SELECT RELEASE_LOCK(%s)", [lock_name])
            except Exception:
                pass


def _claim(key, value, timeout):
    """cache.add made atomic across processes.

    FileBasedCache.add is get-then-set, so two processes could both claim the
    same key; on MySQL the check+set runs under a named lock instead.
    """
    with _mysql_named_lock(key) as has_lock:
        return bool(has_lock and cache.add(key, value, timeout=timeout))


def jobs_enabled():
    if getattr(settings, "TESTING", False):
        return False
    # Default mirrors settings.py: on in production (DEBUG=False), off in dev.
    default = not settings.DEBUG
    return bool(getattr(settings, "BACKGROUND_JOBS_ENABLED", default))


def retry_missing_invoices(
    days=7, min_age_minutes=15, apply=False, max_attempts=None, write=None
):
    """Find (and with apply=True, fulfil) Razorpay-paid subscriptions that
    have no invoice. Returns the number found."""
    from apps.agents.models import AgentSubscription, Invoice
    from apps.agents.services.account_auth import is_real_razorpay_id
    from apps.agents.services.post_payment import fulfill_invoice_and_welcome
    from apps.agents.services.test_markers import TEST_EMAIL_DOMAIN, TEST_PAYMENT_PREFIX

    write = write or (lambda line: None)
    now = datetime.now()
    subs = (
        AgentSubscription.objects.filter(
            payment_status="completed",
            starts_at__gte=now - timedelta(days=days),
            starts_at__lte=now - timedelta(minutes=min_age_minutes),
        )
        .exclude(razorpay_payment_id__isnull=True)
        .exclude(razorpay_payment_id="")
        .exclude(razorpay_payment_id__startswith=TEST_PAYMENT_PREFIX)
        .exclude(agent__email__iendswith="@" + TEST_EMAIL_DOMAIN)
        .select_related("agent")
        .order_by("starts_at")
    )

    missing = 0
    for sub in subs:
        if not is_real_razorpay_id(sub.razorpay_payment_id, "pay_") or not sub.agent:
            continue
        if Invoice.objects.filter(razorpay_payment_id=sub.razorpay_payment_id).exists():
            continue
        missing += 1
        write(
            f"MISSING_INVOICE  sub #{sub.pk}  {sub.razorpay_payment_id}  "
            f"agent #{sub.agent_id} {sub.agent.email}  {sub.selected_plan}  Rs {sub.registration_amount}"
        )
        if not apply:
            continue
        if max_attempts:
            attempts_key = f"bgjobs:invoice-attempts:{sub.pk}"
            attempts = cache.get(attempts_key) or 0
            if attempts >= max_attempts:
                write(
                    f"    skipped: {attempts} automatic attempts already failed; run the command by hand"
                )
                continue
            cache.set(attempts_key, attempts + 1, timeout=7 * 86400)
        # One fulfilment per subscription at a time (command vs. web job).
        lock_key = f"bgjobs:invoice-lock:{sub.pk}"
        if not _claim(lock_key, 1, timeout=30 * 60):
            write("    skipped: another retry is running for it")
            continue
        try:
            if Invoice.objects.filter(
                razorpay_payment_id=sub.razorpay_payment_id
            ).exists():
                continue
            invoice = fulfill_invoice_and_welcome(sub.agent, sub)
            write(f"    invoice={getattr(invoice, 'invoice_number', None)}")
        except Exception as err:
            logger.exception("Invoice retry failed for subscription %s", sub.pk)
            write(f"    failed: {err}")
        finally:
            cache.delete(lock_key)
    return missing


def _invoice_job():
    found = retry_missing_invoices(
        days=2,
        apply=True,
        max_attempts=AUTO_MAX_ATTEMPTS,
        write=lambda line: logger.info("[bgjobs] %s", line),
    )
    if found:
        logger.warning(
            "[bgjobs] retried fulfilment for %s paid subscription(s) without an invoice",
            found,
        )


def _paldi_expiry_job():
    from django.core.management import call_command

    out = StringIO()
    call_command("process_event_referral_expirations", stdout=out)


def _system_load_monitor_job():
    try:
        from apps.admin_panel.services.system_monitor import SystemMonitorService

        SystemMonitorService.check_and_alert(threshold=95.0)
    except Exception as e:
        logger.warning(f"[bgjobs] system-load-monitor check failed: {e}")


WA_LOG_RETENTION_DAYS = 90


def _wa_log_prune_job():
    """Keep the WhatsApp message log bounded: drop rows older than WA_LOG_RETENTION_DAYS in small batches."""
    from apps.wa_agent_bot.models import WaBotMessageLog

    cutoff = datetime.now() - timedelta(days=WA_LOG_RETENTION_DAYS)
    deleted = 0
    while True:
        ids = list(
            WaBotMessageLog.objects.filter(created_at__lt=cutoff).values_list(
                "id", flat=True
            )[:1000]
        )
        if not ids:
            break
        deleted += WaBotMessageLog.objects.filter(id__in=ids).delete()[0]
    if deleted:
        logger.info(
            "[bgjobs] pruned %s WhatsApp message log row(s) older than %s days",
            deleted,
            WA_LOG_RETENTION_DAYS,
        )


DAILY_BACKUP_RETENTION = 14


def _daily_backup_job():
    """Daily mysqldump into backups/ (db_backup_daily_*), keeping the newest 14."""
    from django.core.management import call_command

    # shortcut: backups stay on this host only (unencrypted, same account as the
    # site); copy them offsite, encrypted, once the owner picks a destination.
    try:
        call_command(
            "backup_database",
            tag="daily",
            retention=DAILY_BACKUP_RETENTION,
            stdout=StringIO(),
        )
    except Exception:
        logger.exception("[bgjobs] daily database backup failed")


# (name, interval in seconds, function)
JOBS = (
    ("system-load-monitor", 60, _system_load_monitor_job),
    ("invoice-retry", 60 * 60, _invoice_job),
    ("paldi-expirations", 30 * 60, _paldi_expiry_job),
    ("wa-log-prune", 24 * 60 * 60, _wa_log_prune_job),
    ("daily-db-backup", 24 * 60 * 60, _daily_backup_job),
)


def _run(name, func):
    close_old_connections()
    try:
        func()
    except Exception:
        logger.exception("[bgjobs] job %s failed", name)
    finally:
        close_old_connections()


def maybe_run_due_jobs():
    """Start each job whose interval has passed, at most once across processes."""
    if not jobs_enabled():
        return []
    started = []
    for name, interval, func in JOBS:
        key = f"bgjobs:last-run:{name}"
        try:
            # cache.get first: the cheap common case needs no DB round trip.
            if cache.get(key) or not _claim(
                key, datetime.now().isoformat(), timeout=interval
            ):
                continue
        except Exception:
            continue
        threading.Thread(
            target=_run, args=(name, func), daemon=True, name=f"bgjob-{name}"
        ).start()
        started.append(name)
    return started
