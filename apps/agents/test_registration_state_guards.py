"""Audit 2026-10-01 F-11: anonymous step 1 overwrote name/mobile of agents past
registration (suspended, awaiting approval...) and a later checkout reset a
paid agent's status to pending_payment."""
from unittest.mock import patch

from apps.agents.models import Agent, AgentDraft, AgentSubscription
from apps.agents.signup_test_support import ORDER_A, PAY_A, _SignupBase, _captured_webhook, _rzp


class RegistrationStateGuardTests(_SignupBase):
    def _existing(self, status, email='existing.guard@example.com'):
        return Agent.objects.create(fullname='Original Name', email=email, mobile='9000000101', status=status)

    def _assert_untouched(self, agent, status):
        agent.refresh_from_db()
        self.assertEqual((agent.fullname, agent.mobile, agent.status), ('Original Name', '9000000101', status))

    def test_suspended_agent_cannot_be_resubmitted(self):
        agent = self._existing('suspended')
        r = self._step1(agent.email)
        self.assertEqual(r.status_code, 422)
        self.assertIn('contact support', r.json()['message'])
        self._assert_untouched(agent, 'suspended')

    def test_agent_awaiting_approval_is_sent_to_login(self):
        for status in ('pending_admin_approval', 'event_challenge', 'inactive'):
            agent = self._existing(status, email=f'{status}@example.com')
            r = self._step1(agent.email)
            self.assertEqual(r.status_code, 422, status)
            self.assertEqual(r.json().get('redirect'), '/agent-login/')
            self._assert_untouched(agent, status)

    def test_registration_in_progress_can_still_be_resumed(self):
        for status in ('incomplete', 'pending_payment', 'rejected'):
            agent = self._existing(status, email=f'resume.{status}@example.com')
            r = self._step1(agent.email)
            self.assertEqual(r.status_code, 200, (status, r.content))
            self.assertTrue(r.json()['success'])

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_checkout_after_webhook_activation_does_not_reset_or_recharge(self, _q):
        agent = self._signup('webhook.won@example.com', [ORDER_A])
        paise = self._paise(AgentSubscription.objects.get(razorpay_order_id=ORDER_A))
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(paise)), \
             patch('apps.agents.views.registration.razorpay_webhook_secret', return_value='whsec'):
            self.client.post('/razorpay-webhook/', data=_captured_webhook(ORDER_A, paise),
                             content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE='sig')
        agent.refresh_from_db()
        self.assertEqual(agent.status, 'pending_approval')

        # The plans tab was still open; the user clicks Pay again.
        with patch('apps.agents.views.registration.create_checkout_order',
                   return_value=('order_SECONDCHARGE01', False)) as create:
            r = self.client.post('/agent-register/complete/', data={'plan_type': 'starter'},
                                 content_type='application/json')
        self.assertTrue(r.json().get('already_completed'), r.json())
        create.assert_not_called()
        agent.refresh_from_db()
        self.assertEqual(agent.status, 'pending_approval')
        self.assertEqual(AgentSubscription.objects.filter(agent=agent).count(), 1)

    def test_create_agent_from_draft_leaves_post_registration_agents_alone(self):
        from apps.agents.views.registration import create_agent_from_draft
        agent = self._existing('pending_approval')
        draft = AgentDraft.objects.create(session_key='x', email=agent.email, fullname='Attacker', mobile='9999999999')
        create_agent_from_draft(draft, 'starter', "Starter's Plan")
        self._assert_untouched(agent, 'pending_approval')
