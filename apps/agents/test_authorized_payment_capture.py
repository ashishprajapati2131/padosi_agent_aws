"""Audit 2026-10-01 F-19: an 'authorized' Razorpay payment (only a hold) was
treated as paid. If it is never captured Razorpay releases it, yet the agent
was activated and invoiced. Now an authorized payment is captured first and
only a captured payment activates."""
import json
from unittest.mock import MagicMock, patch

from apps.agents.models import AgentSubscription
from apps.agents.signup_test_support import ORDER_A, PAY_A, _SignupBase


def _client(amount, capture_works):
    client = MagicMock()
    client.utility.verify_payment_signature.return_value = True
    client.utility.verify_webhook_signature.return_value = True
    authorized = {'id': PAY_A, 'order_id': ORDER_A, 'status': 'authorized', 'amount': amount}
    captured = dict(authorized, status='captured')
    after = captured if capture_works else authorized
    client.payment.fetch.side_effect = [authorized, after, after, after]
    client.order.payments.return_value = {'items': [authorized]}
    return client


class AuthorizedPaymentCaptureTests(_SignupBase):
    def _order(self, email):
        agent = self._signup(email, [ORDER_A])
        return agent, self._paise(AgentSubscription.objects.get(razorpay_order_id=ORDER_A))

    def _verify(self, client):
        with patch('apps.agents.views.registration.razorpay_client', return_value=client):
            return self.client.post('/agent-register/verify-payment/', data={
                'razorpay_order_id': ORDER_A, 'razorpay_payment_id': PAY_A,
                'razorpay_signature': 'sig'}, content_type='application/json').json()

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_authorized_payment_is_captured_then_activated(self, _q):
        agent, paise = self._order('auth.capture@example.com')
        client = _client(paise, capture_works=True)
        body = self._verify(client)
        self.assertTrue(body['success'], body)
        client.payment.capture.assert_called_once()
        self.assertEqual(AgentSubscription.objects.get(razorpay_order_id=ORDER_A).payment_status, 'completed')

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_uncapturable_authorized_payment_does_not_activate(self, _q):
        agent, paise = self._order('auth.fail@example.com')
        body = self._verify(_client(paise, capture_works=False))
        self.assertFalse(body['success'])
        self.assertIn('being confirmed', body['message'])
        self.assertEqual(AgentSubscription.objects.get(razorpay_order_id=ORDER_A).payment_status, 'pending')
        agent.refresh_from_db()
        self.assertEqual(agent.status, 'pending_payment')

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_payment_authorized_webhook_does_not_activate(self, _q):
        agent, paise = self._order('auth.webhook@example.com')
        body = json.dumps({'event': 'payment.authorized', 'payload': {'payment': {'entity': {
            'id': PAY_A, 'order_id': ORDER_A, 'amount': paise, 'status': 'authorized'}}}})
        with patch('apps.agents.views.registration.razorpay_client', return_value=_client(paise, True)), \
             patch('apps.agents.views.registration.razorpay_webhook_secret', return_value='whsec'):
            r = self.client.post('/razorpay-webhook/', data=body, content_type='application/json',
                                 HTTP_X_RAZORPAY_SIGNATURE='sig')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(AgentSubscription.objects.get(razorpay_order_id=ORDER_A).payment_status, 'pending')

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_recovery_captures_an_authorized_payment(self, _q):
        from apps.agents.views.registration import verify_and_activate_pending_payment
        agent, paise = self._order('auth.recover@example.com')
        client = _client(paise, capture_works=True)
        client.payment.fetch.side_effect = None
        client.payment.fetch.return_value = {'id': PAY_A, 'order_id': ORDER_A, 'status': 'captured', 'amount': paise}
        with patch('apps.agents.views.registration.razorpay_client', return_value=client):
            self.assertTrue(verify_and_activate_pending_payment(agent))
        client.payment.capture.assert_called_once()
