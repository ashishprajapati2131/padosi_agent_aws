"""Bulk-cart online checkout must only create agents for a captured payment
(CLAUDE.md invariant 10): an 'authorized' payment is a hold, not money."""
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.insurance.models import InsuranceProfile


@override_settings(ALLOWED_HOSTS=['testserver'], RAZORPAY_KEY='rzp_test_k', RAZORPAY_SECRET='s')
class BulkCheckoutCaptureTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user('ins.bulk', 'ins.bulk@example.com', 'x')
        InsuranceProfile.objects.create(user=self.manager, insurance_sub_role='manager')
        self.client.force_login(self.manager)
        session = self.client.session
        session['insurance_bulk_cart'] = [{'fullname': 'Cart Agent', 'email': 'cart.agent@example.com',
                                           'mobile': '9000000999', 'plan_type': 'starter', 'amount': 100}]
        session['insurance_bulk_order_id'] = 'order_BULK1'
        session.save()

    @mock.patch('apps.agents.services.razorpay_checkout.ensure_payment_captured', return_value=None)
    @mock.patch('apps.insurance.views.agents.razorpay')
    def test_uncaptured_payment_creates_no_agents(self, rzp, _captured):
        rzp.Client.return_value.payment.fetch.return_value = {'id': 'pay_1', 'amount': 10000, 'status': 'authorized'}
        resp = self.client.post(reverse('insurance:checkout_online_success'), {
            'razorpay_payment_id': 'pay_1', 'razorpay_order_id': 'order_BULK1', 'razorpay_signature': 'sig'})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(User.objects.filter(email='cart.agent@example.com').exists())
