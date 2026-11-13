"""Section 2 (registration / payment / auth) follow-ups: PAY10, PAY12, PAY13, PAY16."""
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.agents.models import Agent, AgentSubscription
from apps.agents.test_audit_security import _paid_agent


class RenewalPriceTests(SimpleTestCase):  # PAY13
    def test_renewal_matches_signup_whole_rupee_total(self):
        from apps.agents.views.renewal import _renewal_price_paise

        # 1999 + 18% = 2358.82 -> signup charges 2359; truncation used to give 235881 paise.
        self.assertEqual(_renewal_price_paise('starter', {'starter': {'full_price': 1999}}), 235900)
        self.assertEqual(_renewal_price_paise('professional', {}), 1179900)


class InvoiceSplitTests(TestCase):  # PAY13
    def test_base_plus_gst_equals_total(self):
        agent = _paid_agent(email='inv@example.com', mobile='9876500321')
        sub = agent.subscriptions.first()
        sub.registration_amount = Decimal('2359.00')
        sub.save(update_fields=['registration_amount'])
        from apps.agents.services.invoice import InvoiceService

        with patch.object(InvoiceService, 'calculate_discount_percent', return_value=0), \
             patch('apps.agents.services.invoice.Invoice.objects.create', side_effect=RuntimeError('stop')) as create:
            InvoiceService().generate_from_subscription(agent, sub, sync_sheet=False)
        self.assertTrue(create.called)
        kw = create.call_args.kwargs
        self.assertEqual(Decimal(str(kw['base_amount'])), Decimal('1999.15'))
        self.assertEqual(Decimal(str(kw['base_amount'])) + Decimal(str(kw['gst_amount'])),
                         Decimal(str(kw['total_amount'])))


class ActivationReReadsAgentTests(TestCase):  # PAY12
    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_admin_change_made_after_load_is_not_overwritten(self, _q):
        from apps.agents.views.registration import _activate_paid_subscription

        agent = Agent.objects.create(fullname='Old', email='stale@example.com',
                                     mobile='9876500654', status='pending_payment', plan_type='starter')
        sub = AgentSubscription.objects.create(
            agent=agent, selected_plan="Starter's Plan", registration_amount=Decimal('2359'),
            payment_status='pending', status='inactive', razorpay_order_id='order_STALE0000001',
        )
        stale = Agent.objects.get(pk=agent.pk)
        Agent.objects.filter(pk=agent.pk).update(fullname='Fixed By Admin')

        _activate_paid_subscription(stale, sub, {'id': 'pay_STALE0000001'})

        agent.refresh_from_db()
        self.assertEqual(agent.fullname, 'Fixed By Admin')
        self.assertEqual(agent.status, 'pending_approval')


class PaymentCallbackRateLimitTests(TestCase):  # PAY10
    def setUp(self):
        cache.clear()

    def test_anonymous_callbacks_are_capped_per_ip(self):
        with patch('apps.agents.views.registration._recover_pending_razorpay_checkout',
                   return_value=None) as recover:
            for _ in range(25):
                self.client.get('/agent-register/payment-callback/?razorpay_order_id=order_X')
        self.assertEqual(recover.call_count, 20)


class GateResolvesAgentOncePerRequestTests(SimpleTestCase):  # PAY16
    def test_agent_lookup_is_memoised_on_the_request(self):
        from apps.agents.middleware import _request_agent

        request = RequestFactory().get('/agent/dashboard/')
        with patch('apps.agents.middleware.resolve_agent_for_user', return_value='A') as resolve:
            self.assertEqual(_request_agent(request, object()), 'A')
            self.assertEqual(_request_agent(request, object()), 'A')
        self.assertEqual(resolve.call_count, 1)
