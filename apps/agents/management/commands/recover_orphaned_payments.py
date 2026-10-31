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

Captured event-checkout payments whose EventRegistration is still unpaid (tab
closed after capture) are fulfilled with fulfil_event_registration; insurance
portal orders (single agent / bulk cart) with fulfil_insurance_agent_order /
fulfil_insurance_bulk_order.
"""
import time
from functools import partial

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'List (or with --apply, activate) captured registration payments with no activated subscription.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30, help='How far back to scan Razorpay payments (default 30).')
        parser.add_argument('--apply', action='store_true', help='Activate the agents found (default: dry run).')

    def handle(self, *args, **options):
        from apps.agents.models import Agent, AgentSubscription, EventRegistration
        from apps.insurance.models import InsuranceBulkOrder
        from apps.agents.services.account_auth import agent_has_completed_payment
        from apps.agents.services.feature_unlock import PLAN_SLUGS, normalize_plan_slug, plan_slug_from_name
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
                try:
                    event_reg = EventRegistration.objects.filter(razorpay_order_id=order_id).first()
                except Exception:
                    event_reg = None
                if event_reg:
                    found += self._event_order(event_reg, payment, apply)
                    continue
                bulk_order = InsuranceBulkOrder.objects.filter(razorpay_order_id=order_id).first()
                if bulk_order:
                    if bulk_order.status != 'paid':
                        from apps.insurance.views.agents import fulfil_insurance_bulk_order
                        found += self._insurance_order(
                            'INSURANCE_BULK_NOT_FULFILLED',
                            f'bulk order #{bulk_order.pk} status={bulk_order.status} agents={len(bulk_order.cart)}',
                            fulfil_insurance_bulk_order, payment, apply,
                        )
                    continue
                sub = AgentSubscription.objects.filter(razorpay_order_id=order_id).first()
                if sub and sub.payment_status == 'completed':
                    continue

                agent = sub.agent if sub else None
                order_plan = plan_slug_from_name(sub.selected_plan or '') if sub else ''
                if not sub:
                    order = client.order.fetch(order_id)
                    receipt = str(order.get('receipt') or '')
                    if receipt.startswith('evt_'):
                        # A stale order of a registration that has since got a newer one.
                        reg_id = receipt.split('_')[1]
                        try:
                            event_reg = EventRegistration.objects.filter(pk=reg_id).first() if reg_id.isdigit() else None
                        except Exception:
                            event_reg = None
                        if event_reg:
                            found += self._event_order(event_reg, payment, apply)
                        continue
                    if receipt.startswith('agent_ins_'):
                        found += self._insurance_agent_order(order, payment, apply)
                        continue
                    if not receipt.startswith('agent_draft_'):
                        continue  # other checkout
                    notes = order.get('notes') if isinstance(order.get('notes'), dict) else {}
                    agent = Agent.objects.filter(email__iexact=str(notes.get('email') or '')).first()
                    order_plan = str(notes.get('plan_type') or '')

                found += 1
                kind = 'PAID_NOT_ACTIVATED' if sub else 'ORPHANED_ORDER'
                amount = (payment.get('amount') or 0) / 100
                who = f'agent #{agent.pk} {agent.email} status={agent.status}' if agent else 'agent NOT FOUND'
                note = ''
                upgrade = False
                if agent and agent_has_completed_payment(agent):
                    rank = {slug: i for i, slug in enumerate(PLAN_SLUGS)}
                    current = normalize_plan_slug(agent.plan_type or '')
                    if rank.get(order_plan, -1) > rank.get(current, -1):
                        upgrade = True
                        note = f'  <- unactivated UPGRADE {current or "?"} -> {order_plan}'
                    else:
                        note = '  <- agent already has another completed payment: possible DOUBLE CHARGE, refund manually'
                self.stdout.write(f'{kind}  {payment["id"]}  {order_id}  Rs {amount:.2f}  {who}{note}')

                if not apply or not agent or (note and not upgrade):
                    continue
                if not sub and not adopt_orphan_registration_order(order_id):
                    self.stdout.write('    could not rebuild the subscription row; check this order manually')
                    continue
                ok = verify_and_activate_pending_payment(agent, include_paid_agents=upgrade)
                agent.refresh_from_db()
                self.stdout.write(f'    activated={ok}  agent status now {agent.status}')

            if len(items) < 100:
                break
            skip += 100

        mode = 'applied' if apply else 'dry run, nothing changed'
        self.stdout.write(self.style.SUCCESS(f'{found} unactivated registration payment(s) found ({mode}).'))

    def _insurance_agent_order(self, order, payment, apply):
        """Report (and with --apply fulfil) a captured single-agent insurance order."""
        from apps.agents.models import Agent
        from apps.insurance.views.payments import INSURANCE_PAID_STATUSES, fulfil_insurance_agent_order

        notes = order.get('notes') if isinstance(order.get('notes'), dict) else {}
        agent_id = str(notes.get('agent_id') or '')
        agent = Agent.objects.filter(pk=int(agent_id)).first() if agent_id.isdigit() else None
        if agent and agent.payment_reference == payment['id']:
            return 0  # this payment is already recorded
        detail = f'agent #{agent.pk} status={agent.status}' if agent else 'agent NOT FOUND'
        if agent and agent.status in INSURANCE_PAID_STATUSES:
            detail += '  <- already paid another way: possible DOUBLE CHARGE, refund manually'
        return self._insurance_order(
            'INSURANCE_AGENT_NOT_FULFILLED', detail, partial(fulfil_insurance_agent_order, order=order), payment, apply,
        )

    def _insurance_order(self, kind, detail, fulfil, payment, apply):
        amount = (payment.get('amount') or 0) / 100
        self.stdout.write(f'{kind}  {payment["id"]}  {payment["order_id"]}  Rs {amount:.2f}  {detail}')
        if apply:
            try:
                _obj, fulfilled = fulfil(payment['order_id'], payment['id'], payment=payment)
                self.stdout.write(f'    fulfilled={fulfilled}')
            except Exception as exc:  # InsurancePaymentRejected or a DB error: report, keep scanning
                self.stdout.write(f'    not fulfilled: {exc}')
        return 1

    def _event_order(self, event_reg, payment, apply):
        """Report (and with --apply fulfil) a captured payment of an unpaid event registration."""
        from apps.agents.views.events import fulfil_event_registration

        if event_reg.payment_status == 'success':
            return 0
        amount = (payment.get('amount') or 0) / 100
        self.stdout.write(
            f'EVENT_NOT_FULFILLED  {payment["id"]}  {payment["order_id"]}  Rs {amount:.2f}  '
            f'event registration #{event_reg.pk} {event_reg.email}'
        )
        if apply:
            try:
                _reg, fulfilled = fulfil_event_registration(
                    event_reg.pk, payment['order_id'], payment['id'], payment=payment,
                )
                self.stdout.write(f'    fulfilled={fulfilled}')
            except Exception as exc:  # EventPaymentRejected or a DB error: report, keep scanning
                self.stdout.write(f'    not fulfilled: {exc}')
        return 1
