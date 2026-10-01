"""Find captured Razorpay registration payments that never activated an agent.

Before one-subscription-row-per-order, retrying checkout re-pointed the
agent's pending row at the new order. A customer who then paid the earlier
order was charged but never activated (and never reached Admin -> Approvals).

Dry run (default) only lists what it finds. --apply rebuilds the lost
subscription row from the order's own notes and runs the normal recovery
(verify_and_activate_pending_payment), which re-checks the payment with
Razorpay, verifies the amount and sends the invoice + welcome email.

    python manage.py recover_orphaned_payments --days 60
    python manage.py recover_orphaned_payments --days 60 --apply
"""
import time

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'List (or with --apply, activate) captured registration payments with no activated subscription.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30, help='How far back to scan Razorpay payments (default 30).')
        parser.add_argument('--apply', action='store_true', help='Activate the agents found (default: dry run).')

    def handle(self, *args, **options):
        from apps.agents.models import Agent, AgentSubscription
        from apps.agents.services.account_auth import agent_has_completed_payment
        from apps.agents.services.razorpay_checkout import razorpay_client
        from apps.agents.views.registration import (
            adopt_orphan_registration_order,
            verify_and_activate_pending_payment,
        )

        client = razorpay_client()
        if client is None:
            self.stderr.write('Razorpay keys are not configured.')
            return

        apply = options['apply']
        since = int(time.time()) - options['days'] * 86400
        found = 0
        skip = 0
        while True:
            page = client.payment.all({'from': since, 'count': 100, 'skip': skip}) or {}
            items = page.get('items') or []
            for payment in items:
                if payment.get('status') != 'captured' or not payment.get('order_id'):
                    continue
                order_id = payment['order_id']
                sub = AgentSubscription.objects.filter(razorpay_order_id=order_id).first()
                if sub and sub.payment_status == 'completed':
                    continue

                agent = sub.agent if sub else None
                if not sub:
                    order = client.order.fetch(order_id)
                    if not str(order.get('receipt') or '').startswith('agent_draft_'):
                        continue  # insurance / events / other checkout
                    notes = order.get('notes') if isinstance(order.get('notes'), dict) else {}
                    agent = Agent.objects.filter(email__iexact=str(notes.get('email') or '')).first()

                found += 1
                kind = 'PAID_NOT_ACTIVATED' if sub else 'ORPHANED_ORDER'
                amount = (payment.get('amount') or 0) / 100
                who = f'agent #{agent.pk} {agent.email} status={agent.status}' if agent else 'agent NOT FOUND'
                note = ''
                if agent and agent_has_completed_payment(agent):
                    note = '  <- agent already has another completed payment: possible DOUBLE CHARGE, refund manually'
                self.stdout.write(f'{kind}  {payment["id"]}  {order_id}  Rs {amount:.2f}  {who}{note}')

                if not apply or not agent or note:
                    continue
                if not sub and not adopt_orphan_registration_order(order_id):
                    self.stdout.write('    could not rebuild the subscription row; check this order manually')
                    continue
                ok = verify_and_activate_pending_payment(agent)
                agent.refresh_from_db()
                self.stdout.write(f'    activated={ok}  agent status now {agent.status}')

            if len(items) < 100:
                break
            skip += 100

        mode = 'applied' if apply else 'dry run, nothing changed'
        self.stdout.write(self.style.SUCCESS(f'{found} unactivated registration payment(s) found ({mode}).'))
