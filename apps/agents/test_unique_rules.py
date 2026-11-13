"""One invoice per Razorpay payment (PAY13) and one championship credit per referred agent (CH4)."""
from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.agents.models import Agent, AgentSubscription, Invoice
from apps.agents.test_audit_security import _paid_agent


def _invoice(agent, number, payment_id):
    return Invoice.objects.create(
        invoice_number=number, agent=agent, agent_name='A', agent_email='a@example.com',
        agent_mobile='9876500777', agent_state='Gujarat', plan_name='Starter', plan_type='starter',
        base_amount=Decimal('1999'), gst_amount=Decimal('360'), total_amount=Decimal('2359'),
        discount_folder='0', razorpay_payment_id=payment_id, payment_status='paid',
    )


class InvoiceUniquePaymentTests(TestCase):
    def test_second_invoice_for_same_payment_is_refused(self):
        agent = _paid_agent(email='uq1@example.com', mobile='9876500771')
        _invoice(agent, 'INV-1', 'pay_DUPLICATE01')
        with self.assertRaises(IntegrityError), transaction.atomic():
            _invoice(agent, 'INV-2', 'pay_DUPLICATE01')

    def test_many_invoices_without_payment_id_are_fine(self):
        agent = _paid_agent(email='uq2@example.com', mobile='9876500772')
        _invoice(agent, 'INV-3', None)
        _invoice(agent, 'INV-4', None)
        self.assertEqual(Invoice.objects.filter(razorpay_payment_id__isnull=True).count(), 2)

    def test_service_returns_existing_invoice_on_clash(self):
        from apps.agents.services.invoice import InvoiceService

        agent = _paid_agent(email='uq3@example.com', mobile='9876500773')
        sub = agent.subscriptions.first()
        existing = _invoice(agent, 'INV-5', sub.razorpay_payment_id)
        # The early "already exists" check misses it (race), then the insert hits the rule.
        real_filter = Invoice.objects.filter
        calls = {'n': 0}

        def racy_filter(*a, **k):
            calls['n'] += 1
            return real_filter(pk=-1) if calls['n'] == 1 else real_filter(*a, **k)

        with patch.object(Invoice.objects, 'filter', side_effect=racy_filter), \
             patch.object(InvoiceService, 'generate_pdf', return_value=None),              patch.object(InvoiceService, 'calculate_discount_percent', return_value=0):
            got = InvoiceService().generate_from_subscription(agent, sub, sync_sheet=False)
        self.assertEqual(got.pk, existing.pk)


class ChampionshipReferralUniqueTests(TestCase):
    def test_same_agent_cannot_be_credited_twice_in_a_campaign(self):
        from apps.referral_championship.models import ChampionshipReferral
        from apps.referral_championship.services.attribution_service import get_or_create_participant
        from apps.referral_championship.testing import live_campaign

        campaign = live_campaign()
        referrer = Agent.objects.create(fullname='R', email='ref@example.com', mobile='9876500781', status='active')
        referred = Agent.objects.create(fullname='N', email='new@example.com', mobile='9876500782', status='active')
        part = get_or_create_participant(referrer, campaign)
        ChampionshipReferral.objects.create(campaign=campaign, referrer=part, referred_agent=referred,
                                            referral_id=part.referral_id)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChampionshipReferral.objects.create(campaign=campaign, referrer=part, referred_agent=referred,
                                                referral_id=part.referral_id)
        # Rows with no referred agent yet (link opened, no signup) may repeat.
        ChampionshipReferral.objects.create(campaign=campaign, referrer=part, referral_id=part.referral_id)
        ChampionshipReferral.objects.create(campaign=campaign, referrer=part, referral_id=part.referral_id)
