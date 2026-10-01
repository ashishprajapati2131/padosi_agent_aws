"""Scheduled jobs without cron, for shared hosting.

cPanel cron did not run reliably on this host (and was reverted in
236fd60), and a forever-looping thread dies whenever Passenger recycles or
idles the app process. So jobs are triggered by traffic instead:
BackgroundJobsMiddleware calls maybe_run_due_jobs() after each response. A
job whose interval has passed is claimed with cache.add (Redis or the file
cache, shared by every app process) and runs once in a daemon thread. If the
thread dies, the claim simply expires and the next request after the
interval runs it again; every job is safe to re-run.

On only when settings.BACKGROUND_JOBS_ENABLED (default: on when DEBUG is
off) and never during tests. Audit 2026-10-01 F-21 / F-39.
"""
import logging
import threading
from datetime import datetime, timedelta
from io import StringIO

from django.conf import settings
from django.core.cache import cache
from django.db import close_old_connections

logger = logging.getLogger(__name__)

# Automatic retries per subscription, so a permanently failing invoice does
# not resend the welcome email every hour.
AUTO_MAX_ATTEMPTS = 3


def jobs_enabled():
    if getattr(settings, 'TESTING', False):
        return False
    return bool(getattr(settings, 'BACKGROUND_JOBS_ENABLED', False))


def retry_missing_invoices(days=7, min_age_minutes=15, apply=False, max_attempts=None, write=None):
    """Find (and with apply=True, fulfil) Razorpay-paid subscriptions that
    have no invoice. Returns the number found."""
    from apps.agents.models import AgentSubscription, Invoice
    from apps.agents.services.account_auth import is_real_razorpay_id
    from apps.agents.services.post_payment import fulfill_invoice_and_welcome
    from apps.agents.services.test_markers import TEST_EMAIL_DOMAIN, TEST_PAYMENT_PREFIX

    write = write or (lambda line: None)
    now = datetime.now()
    subs = (AgentSubscription.objects
            .filter(payment_status='completed',
                    starts_at__gte=now - timedelta(days=days),
                    starts_at__lte=now - timedelta(minutes=min_age_minutes))
            .exclude(razorpay_payment_id__isnull=True).exclude(razorpay_payment_id='')
            .exclude(razorpay_payment_id__startswith=TEST_PAYMENT_PREFIX)
            .exclude(agent__email__iendswith='@' + TEST_EMAIL_DOMAIN)
            .select_related('agent').order_by('starts_at'))

    missing = 0
    for sub in subs:
        if not is_real_razorpay_id(sub.razorpay_payment_id, 'pay_') or not sub.agent:
            continue
        if Invoice.objects.filter(razorpay_payment_id=sub.razorpay_payment_id).exists():
            continue
        missing += 1
        write(f'MISSING_INVOICE  sub #{sub.pk}  {sub.razorpay_payment_id}  '
              f'agent #{sub.agent_id} {sub.agent.email}  {sub.selected_plan}  Rs {sub.registration_amount}')
        if not apply:
            continue
        if max_attempts:
            attempts_key = f'bgjobs:invoice-attempts:{sub.pk}'
            attempts = cache.get(attempts_key) or 0
            if attempts >= max_attempts:
                write(f'    skipped: {attempts} automatic attempts already failed; run the command by hand')
                continue
            cache.set(attempts_key, attempts + 1, timeout=7 * 86400)
        # One fulfilment per subscription at a time (command vs. web job).
        lock_key = f'bgjobs:invoice-lock:{sub.pk}'
        if not cache.add(lock_key, 1, timeout=30 * 60):
            write('    skipped: another retry is running for it')
            continue
        try:
            if Invoice.objects.filter(razorpay_payment_id=sub.razorpay_payment_id).exists():
                continue
            invoice = fulfill_invoice_and_welcome(sub.agent, sub)
            write(f'    invoice={getattr(invoice, "invoice_number", None)}')
        except Exception as err:
            logger.exception('Invoice retry failed for subscription %s', sub.pk)
            write(f'    failed: {err}')
        finally:
            cache.delete(lock_key)
    return missing


def _invoice_job():
    found = retry_missing_invoices(days=2, apply=True, max_attempts=AUTO_MAX_ATTEMPTS,
                                   write=lambda line: logger.info('[bgjobs] %s', line))
    if found:
        logger.warning('[bgjobs] retried fulfilment for %s paid subscription(s) without an invoice', found)


def _paldi_expiry_job():
    from django.core.management import call_command
    out = StringIO()
    call_command('process_event_referral_expirations', stdout=out)
    logger.info('[bgjobs] paldi expirations: %s', out.getvalue().strip())


# (name, interval in seconds, function)
JOBS = (
    ('invoice-retry', 60 * 60, _invoice_job),
    ('paldi-expirations', 30 * 60, _paldi_expiry_job),
)


def _run(name, func):
    close_old_connections()
    try:
        func()
    except Exception:
        logger.exception('[bgjobs] job %s failed', name)
    finally:
        close_old_connections()


def maybe_run_due_jobs():
    """Start each job whose interval has passed, at most once across processes."""
    if not jobs_enabled():
        return []
    started = []
    for name, interval, func in JOBS:
        key = f'bgjobs:last-run:{name}'
        try:
            if cache.get(key) or not cache.add(key, datetime.now().isoformat(), timeout=interval):
                continue
        except Exception:
            continue
        threading.Thread(target=_run, args=(name, func), daemon=True, name=f'bgjob-{name}').start()
        started.append(name)
    return started
