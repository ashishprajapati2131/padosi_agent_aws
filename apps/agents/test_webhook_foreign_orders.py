"""Audit 2026-10-01 F-20: the Razorpay webhook returned 503 for every order
without an agent subscription (insurance / event checkouts never store one),
so Razorpay retried them forever and could disable the endpoint."""
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class WebhookForeignOrderTests(TestCase):
    def _webhook(self, order_id, order=None, fetch_error=False):
        client = MagicMock()
        client.utility.verify_webhook_signature.return_value = True
        if fetch_error:
            client.order.fetch.side_effect = Exception('Razorpay unreachable')
        else:
            client.order.fetch.return_value = order
        body = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': {
            'id': 'pay_FOREIGN00000001', 'order_id': order_id, 'amount': 100, 'status': 'captured'}}}})
        with patch('apps.agents.views.registration.razorpay_client', return_value=client), \
             patch('apps.agents.views.registration.razorpay_webhook_secret', return_value='whsec'):
            return self.client.post('/razorpay-webhook/', data=body, content_type='application/json',
                                    HTTP_X_RAZORPAY_SIGNATURE='sig').status_code

    def test_insurance_order_is_acknowledged(self):
        order = {'id': 'order_INSURANCE0001', 'receipt': 'agent_ins_5_1700000000', 'notes': {}}
        self.assertEqual(self._webhook('order_INSURANCE0001', order), 200)

    def test_event_order_is_acknowledged(self):
        order = {'id': 'order_EVENTORDER001', 'receipt': 'evt_3_1700000000', 'notes': {}}
        self.assertEqual(self._webhook('order_EVENTORDER001', order), 200)

    def test_unknown_agent_order_is_still_retried(self):
        order = {'id': 'order_AGENTUNKNOWN1', 'receipt': 'agent_upgrade_9_1700000000', 'notes': {}}
        self.assertEqual(self._webhook('order_AGENTUNKNOWN1', order), 503)

    def test_unknown_receipt_is_still_retried(self):
        self.assertEqual(self._webhook('order_LEGACYFORMAT1', {'id': 'x', 'receipt': 'old_format_12'}), 503)

    def test_razorpay_unreachable_is_still_retried(self):
        self.assertEqual(self._webhook('order_UNREACHABLE01', fetch_error=True), 503)
