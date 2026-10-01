"""Audit 2026-10-01 F-31: the offline payment reference is stored as the
subscription's razorpay_order_id, so a reference typed as "order_..." passed
the real-payment dashboard gate; a future payment date also set the expiry."""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.agents.models import Agent, AgentSubscription
from apps.agents.services.account_auth import agent_has_completed_payment
from apps.insurance.models import InsuranceProfile


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class OfflinePaymentReferenceTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user('ins.mgr', 'ins.mgr@example.com', 'x')
        InsuranceProfile.objects.create(user=self.manager, insurance_sub_role='manager')
        self.agent = Agent.objects.create(fullname='Off', email='offline@example.com', mobile='9000000141',
                                          status='pending_accounts_payment', insurance_id=self.manager.id)
        self.sub = AgentSubscription.objects.create(agent=self.agent, selected_plan="Starter's Plan",
                                                    registration_amount='2359.00', payment_status='pending')
        self.client.force_login(self.manager)

    def _record(self, reference, when=None):
        return self.client.post(
            reverse('insurance:record_payment', args=[self.agent.pk]),
            {'payment_method': 'neft', 'payment_reference': reference,
             'payment_recorded_at': (when or date.today()).isoformat()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

    def test_razorpay_looking_reference_is_refused(self):
        resp = self._record('order_FAKE12345678')
        self.assertEqual(resp.status_code, 400)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, 'pending_accounts_payment')
        self.assertFalse(agent_has_completed_payment(self.agent))

    def test_future_payment_date_is_refused(self):
        resp = self._record('UTR123456789', when=date.today() + timedelta(days=30))
        self.assertEqual(resp.status_code, 400)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.payment_status, 'pending')

    def test_real_bank_reference_still_records(self):
        resp = self._record('UTR123456789')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.agent.refresh_from_db()
        self.sub.refresh_from_db()
        self.assertEqual(self.agent.status, 'pending_admin_approval')
        self.assertEqual((self.sub.payment_status, self.sub.razorpay_order_id), ('completed', 'UTR123456789'))
