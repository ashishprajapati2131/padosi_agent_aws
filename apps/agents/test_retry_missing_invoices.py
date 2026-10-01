"""Audit 2026-10-01 F-21: invoice + welcome email ran once in an in-process
thread and nothing retried them after a crash or worker recycle."""
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase

from apps.agents.models import Agent, AgentSubscription, Invoice


class RetryMissingInvoicesTests(TestCase):
    def setUp(self):
        self.agent = Agent.objects.create(fullname='Inv', email='inv.retry@example.com', mobile='9000000151')
        hour_ago = datetime.now() - timedelta(hours=1)
        self.missing = AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Starter's Plan", registration_amount='2359.00',
            payment_status='completed', status='active', starts_at=hour_ago,
            razorpay_order_id='order_NOINVOICE0001', razorpay_payment_id='pay_NOINVOICE00001')
        done = AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Starter's Plan", registration_amount='2359.00',
            payment_status='completed', status='inactive', starts_at=hour_ago,
            razorpay_order_id='order_HASINVOICE001', razorpay_payment_id='pay_HASINVOICE0001')
        Invoice.objects.create(invoice_number='PA/T/1', agent=self.agent, agent_name='Inv', agent_email=self.agent.email,
                               plan_name="Starter's Plan", base_amount=2000, gst_amount=359, total_amount=2359,
                               razorpay_payment_id=done.razorpay_payment_id, payment_status='paid')
        AgentSubscription.objects.create(   # just paid: its background job may still run
            agent=self.agent, selected_plan="Starter's Plan", registration_amount='2359.00',
            payment_status='completed', status='inactive', starts_at=datetime.now(),
            razorpay_order_id='order_FRESHPAID0001', razorpay_payment_id='pay_FRESHPAID00001')

    def _run(self, *args):
        out = StringIO()
        with patch('apps.agents.services.post_payment.fulfill_invoice_and_welcome',
                   return_value=MagicMock(invoice_number='PA/T/2')) as fulfil:
            call_command('retry_missing_invoices', *args, stdout=out)
        return out.getvalue(), fulfil

    def test_dry_run_lists_only_the_missing_one(self):
        out, fulfil = self._run('--days', '2')
        self.assertIn('pay_NOINVOICE00001', out)
        self.assertNotIn('pay_HASINVOICE0001', out)
        self.assertNotIn('pay_FRESHPAID00001', out)
        fulfil.assert_not_called()

    def test_apply_fulfils_it(self):
        out, fulfil = self._run('--days', '2', '--apply')
        fulfil.assert_called_once()
        self.assertEqual(fulfil.call_args.args[1].pk, self.missing.pk)
