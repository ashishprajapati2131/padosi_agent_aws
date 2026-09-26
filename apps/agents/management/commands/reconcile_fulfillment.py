import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.agents.models import AgentSubscription, Invoice
from apps.agents.services.post_payment import fulfill_invoice_and_welcome
from apps.agents.services.invoice import invoice_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reconciles unfulfilled subscriptions (missing invoice, unsent welcome email, or unsynced Google Sheet)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of subscriptions to process in one run. Default is 50.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report unfulfilled subscriptions without making any changes or sending emails.',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        dry_run = options['dry_run']

        self.stdout.write("==> Scanning for completed subscriptions needing fulfillment...")

        completed_subs = AgentSubscription.objects.filter(
            payment_status='completed'
        ).select_related('agent').order_by('-id')[:limit]

        reconciled_invoices = 0
        reconciled_syncs = 0

        for sub in completed_subs:
            agent = sub.agent
            if not agent:
                continue

            # 1. Check if invoice exists for this subscription order/agent
            invoice = None
            if sub.razorpay_order_id:
                invoice = Invoice.objects.filter(razorpay_order_id=sub.razorpay_order_id).first()
            if not invoice and sub.razorpay_payment_id:
                invoice = Invoice.objects.filter(razorpay_payment_id=sub.razorpay_payment_id).first()
            if not invoice:
                invoice = Invoice.objects.filter(agent=agent, plan_name=sub.selected_plan).first()

            if not invoice:
                self.stdout.write(
                    self.style.WARNING(
                        f"Found unfulfilled subscription: Sub #{sub.id} (Agent: {agent.email}, Plan: {sub.selected_plan})"
                    )
                )
                if not dry_run:
                    try:
                        invoice = fulfill_invoice_and_welcome(agent, sub)
                        reconciled_invoices += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"   [RECONCILED] Generated invoice & sent welcome email for Agent #{agent.id}."
                            )
                        )
                    except Exception as err:
                        self.stdout.write(
                            self.style.ERROR(
                                f"   [FAILED] Could not reconcile Sub #{sub.id}: {err}"
                            )
                        )
            elif invoice and not invoice.synced_to_sheet:
                self.stdout.write(
                    self.style.WARNING(
                        f"Found unsynced invoice: {invoice.invoice_number} (Agent: {agent.email})"
                    )
                )
                if not dry_run:
                    try:
                        invoice_service.sync_to_google_sheet(invoice)
                        reconciled_syncs += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"   [SYNCED] Invoice {invoice.invoice_number} synced to Google Sheets."
                            )
                        )
                    except Exception as err:
                        self.stdout.write(
                            self.style.ERROR(
                                f"   [FAILED] Google Sheet sync failed for invoice {invoice.invoice_number}: {err}"
                            )
                        )

        status_msg = f"Done. Reconciled {reconciled_invoices} missing invoices, {reconciled_syncs} Google Sheet syncs."
        if dry_run:
            status_msg = f"[DRY RUN] {status_msg}"
        self.stdout.write(self.style.SUCCESS(f"==> {status_msg}"))
