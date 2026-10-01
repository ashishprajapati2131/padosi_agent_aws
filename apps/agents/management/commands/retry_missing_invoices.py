"""Re-run invoice + welcome email for paid subscriptions that never got them.

Fulfilment runs once in a background thread after payment; if the worker is
recycled or the PDF/email step crashes, nothing retries it. This command
finds completed Razorpay-paid subscriptions without an invoice and runs the
normal fulfilment (invoice PDF, welcome email, Google Sheet sync) for them.

Dry run by default. The website already runs this hourly by itself
(apps/agents/services/background_jobs.py); use the command by hand, e.g.:
    python manage.py retry_missing_invoices --days 60 --apply
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'List (or with --apply, fulfil) paid subscriptions that have no invoice.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7, help='Look back this many days (default 7).')
        parser.add_argument('--apply', action='store_true', help='Generate the invoice and send the email.')
        parser.add_argument('--min-age-minutes', type=int, default=15,
                            help='Skip payments newer than this (their background job may still be running).')

    def handle(self, *args, **options):
        from apps.agents.services.background_jobs import retry_missing_invoices

        missing = retry_missing_invoices(days=options['days'], min_age_minutes=options['min_age_minutes'],
                                         apply=options['apply'], write=self.stdout.write)
        mode = 'applied' if options['apply'] else 'dry run, nothing changed'
        self.stdout.write(self.style.SUCCESS(f'{missing} paid subscription(s) without an invoice ({mode}).'))
