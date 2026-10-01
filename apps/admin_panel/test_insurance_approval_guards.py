"""Audit 2026-10-01 F-15: insurance onboarding approve/reject had no state
check (any agent id became active; a repeat POST re-sent invoice and email)
and reject marked a received payment as failed."""
from unittest.mock import MagicMock, patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.agents.models import Agent, AgentSubscription


class InsuranceApprovalGuardTests(TestCase):
    def setUp(self):
        self.agent = Agent.objects.create(fullname='Ins', email='ins.guard@example.com', mobile='9000000081',
                                          status='pending_admin_approval')
        self.sub = AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Starter's Plan", registration_amount='2359.00',
            payment_status='completed', status='inactive', razorpay_order_id='UTR123456')

    def _post(self, view, **data):
        request = RequestFactory().post('/admin/insurance-approvals/x/', data)
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch('apps.admin_panel.views.insurance_approvals._get_admin_from_session', return_value=1), \
             patch('apps.admin_panel.views.insurance_approvals.ReferralCode'):
            return view(request, self.agent.pk)

    def test_double_approve_sends_one_invoice_and_email(self):
        from apps.admin_panel.views.insurance_approvals import insurance_approvals_approve_onboarding
        invoice, email = MagicMock(), MagicMock()
        invoice.generate_from_subscription.return_value = None
        with patch('apps.agents.services.invoice.invoice_service', invoice), \
             patch('apps.agents.services.brevo.email_service', email):
            self._post(insurance_approvals_approve_onboarding)
            self._post(insurance_approvals_approve_onboarding)
        self.agent.refresh_from_db()
        self.sub.refresh_from_db()
        self.assertEqual((self.agent.status, self.sub.status), ('active', 'active'))
        self.assertEqual(invoice.generate_from_subscription.call_count, 1)
        self.assertEqual(email.send_welcome.call_count, 1)

    def test_agent_not_awaiting_approval_is_not_activated(self):
        from apps.admin_panel.views.insurance_approvals import insurance_approvals_approve_onboarding
        self.agent.status = 'suspended'
        self.agent.save()
        email = MagicMock()
        with patch('apps.agents.services.brevo.email_service', email):
            self._post(insurance_approvals_approve_onboarding)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, 'suspended')
        email.send_welcome.assert_not_called()

    def test_reject_keeps_the_received_payment_completed(self):
        from apps.admin_panel.views.insurance_approvals import insurance_approvals_reject_onboarding
        self.sub.status = 'active'
        self.sub.save()
        self._post(insurance_approvals_reject_onboarding, admin_note='Wrong documents')
        self.agent.refresh_from_db()
        self.sub.refresh_from_db()
        self.assertEqual(self.agent.status, 'rejected')
        self.assertEqual((self.sub.payment_status, self.sub.status), ('completed', 'inactive'))

    def test_reject_ignores_agents_not_awaiting_approval(self):
        from apps.admin_panel.views.insurance_approvals import insurance_approvals_reject_onboarding
        self.agent.status = 'active'
        self.agent.save()
        self._post(insurance_approvals_reject_onboarding, admin_note='x')
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, 'active')
