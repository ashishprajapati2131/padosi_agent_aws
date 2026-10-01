"""Shared fixtures for the signup / payment regression tests (not a test module).

Razorpay is mocked at the gateway boundary, like test_registration_e2e.py.
"""
import json
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.agents.models import Agent
from apps.home.models import SiteSetting
from apps.home.models.pincode import Pincode

ORDER_A = 'order_TKOVAAAAAAAAA1'
ORDER_B = 'order_TKOVBBBBBBBBB2'
PAY_A = 'pay_TKOVAAAAAAAAAA1'


def _rzp(amount_paise, order_payments=None, order=None):
    client = MagicMock()
    client.utility.verify_payment_signature.return_value = True
    client.utility.verify_webhook_signature.return_value = True
    client.payment.fetch.return_value = {'status': 'captured', 'amount': amount_paise}
    client.order.payments.side_effect = lambda oid: {'items': (order_payments or {}).get(oid, [])}
    client.order.fetch.return_value = order or {}
    return client


def _captured_webhook(order_id, amount_paise):
    return json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': {
        'id': PAY_A, 'order_id': order_id, 'amount': amount_paise, 'status': 'captured'}}}})


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class _SignupBase(TestCase):
    def setUp(self):
        cache.clear()
        Pincode.objects.create(
            pincode='380001', office_name='Ahmedabad GPO', district='Ahmedabad',
            state='Gujarat', latitude='23.02250000', longitude='72.57140000',
        )
        SiteSetting.set_value('pricing_config', {
            'starter': {'name': "Starter's Plan", 'full_price': 1999},
            'professional': {'name': "Professional's Plan", 'full_price': 4999},
        }, 'pricing')
        SiteSetting.set_value('trial_plan_config', {'price': 99, 'duration_days': 30}, 'pricing')

    def _step1(self, email):
        return self.client.post('/agent-register-step1/', {
            'fullname': 'Test Agent', 'email': email, 'mobile': '9876543210',
            'agent_pincode': '380001', 'state': 'Gujarat', 'experience_range': '5',
            'segments[]': ['life'],
        })

    def _signup(self, email, order_ids, plans=None):
        r = self._step1(email)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['success'], r.json())
        self.client.post('/agent-register-step2/', {'bio': 'x'})
        self.client.get('/chooseplan/')
        for i, oid in enumerate(order_ids):
            plan = (plans or ['starter'] * len(order_ids))[i]
            with patch('apps.agents.views.registration.create_checkout_order', return_value=(oid, False)):
                rr = self.client.post('/agent-register/complete/', data={'plan_type': plan},
                                      content_type='application/json')
            self.assertEqual(rr.status_code, 200, rr.content)
        return Agent.objects.get(email=email)

    @staticmethod
    def _paise(sub):
        return int(round(float(sub.registration_amount) * 100))
