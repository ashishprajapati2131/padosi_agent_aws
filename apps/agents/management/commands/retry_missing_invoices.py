"""Re-run invoice + welcome email for paid subscriptions that never got them.

Fulfilment runs once in a background thread after payment; if the worker is
recycled or the PDF/email step crashes, nothing retries it. This command
finds completed Razorpay-paid subscriptions without an invoice and runs the
normal fulfilment (invoice PDF, welcome email, Google Sheet sync) for them.

Dry run by default. Suggested cPanel cron (hourly):
    python manage.py retry_missing_invoices --days 2 --apply
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'List (or with --apply, fulfil) paid subscriptions that have no invoice.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7, help='Look back this many days (default 7).')
        parser.add_argument('--apply', action='store_true', help='Generate the invoice and send the email.')
        parser.add_argument('--min-age-minutes', type=int, default=15,
                            help='Skip payments newer than this (their background job may still be running).')

    def handle(self, *args, **options):
        from apps.agents.models import AgentSubscription, Invoice
        from apps.agents.services.account_auth import is_real_razorpay_id
        from apps.agents.services.post_payment import fulfill_invoice_and_welcome

        now = datetime.now()
        since = now - timedelta(days=options['days'])
        settled_before = now - timedelta(minutes=options['min_age_minutes'])
        subs = (AgentSubscription.objects
                .filter(payment_status='completed', starts_at__gte=since, starts_at__lte=settled_before)
                .exclude(razorpay_payment_id__isnull=True).exclude(razorpay_payment_id='')
                .select_related('agent').order_by('starts_at'))

        missing = 0
        for sub in subs:
            if not is_real_razorpay_id(sub.razorpay_payment_id, 'pay_') or not sub.agent:
                continue
            if Invoice.objects.filter(razorpay_payment_id=sub.razorpay_payment_id).exists():
                continue
            missing += 1
            self.stdout.write(f'MISSING_INVOICE  sub #{sub.pk}  {sub.razorpay_payment_id}  '
                              f'agent #{sub.agent_id} {sub.agent.email}  {sub.selected_plan}  Rs {sub.registration_amount}')
            if options['apply']:
                try:
                    invoice = fulfill_invoice_and_welcome(sub.agent, sub)
                    self.stdout.write(f'    invoice={getattr(invoice, "invoice_number", None)}')
                except Exception as err:
                    self.stdout.write(f'    failed: {err}')

        mode = 'applied' if options['apply'] else 'dry run, nothing changed'
        self.stdout.write(self.style.SUCCESS(f'{missing} paid subscription(s) without an invoice ({mode}).'))
