"""Audit 2026-10-01 F-35: promo codes were saved on the subscription even when
they did not apply to the plan (and later counted), Rs 0 checkouts never
counted their use (so max_uses did not hold), and a free-trial promo's own
trial length was shown but not used."""
from datetime import datetime, timedelta
from unittest.mock import patch

from apps.agents.models import Agent, AgentSubscription, PromoCode
from apps.agents.signup_test_support import ORDER_A, PAY_A, _SignupBase, _rzp


class PromoAccountingTests(_SignupBase):
    def _checkout(self, email, plan, promo_code, order_id=ORDER_A):
        r = self._step1(email)
        self.assertTrue(r.json()['success'], r.json())
        self.client.post('/agent-register-step2/', {'bio': 'x'})
        self.client.get('/chooseplan/')
        session = self.client.session
        session['applied_promo_code'] = promo_code
        session.save()
        with patch('apps.agents.views.registration.create_checkout_order', return_value=(order_id, False)):
            resp = self.client.post('/agent-register/complete/', data={'plan_type': plan},
                                    content_type='application/json')
        self.assertEqual(resp.status_code, 200, resp.content)
        return Agent.objects.get(email=email)

    def test_promo_for_another_plan_is_not_stored(self):
        PromoCode.objects.create(code='PROONLY', discount_type='percentage', discount_value=10,
                                 applicable_plan='professional')
        agent = self._checkout('promo.other@example.com', 'starter', 'PROONLY')
        self.assertIsNone(AgentSubscription.objects.get(agent=agent).promo_code)

    def test_applied_promo_is_stored(self):
        PromoCode.objects.create(code='START10', discount_type='percentage', discount_value=10,
                                 applicable_plan='basic')
        agent = self._checkout('promo.starter@example.com', 'starter', 'START10')
        self.assertEqual(AgentSubscription.objects.get(agent=agent).promo_code, 'START10')

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_free_trial_promo_counts_use_and_sets_its_own_length(self, _q):
        PromoCode.objects.create(code='FREE60', discount_type='percentage', discount_value=0, max_uses=5,
                                 is_free_trial=True, trial_duration_days=60, trial_price_override=0)
        agent = self._checkout('promo.free@example.com', 'free_trial', 'FREE60', order_id=None)
        sub = AgentSubscription.objects.get(agent=agent)
        self.assertEqual(sub.payment_status, 'completed')
        self.assertEqual(PromoCode.objects.get(code='FREE60').times_used, 1)
        agent.refresh_from_db()
        self.assertGreater(agent.trial_ends_at, datetime.now() + timedelta(days=59))

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_paid_trial_with_promo_length_on_activation(self, _q):
        from apps.agents.views.registration import verify_and_activate_pending_payment
        PromoCode.objects.create(code='TRIAL45', discount_type='percentage', discount_value=0,
                                 is_free_trial=True, trial_duration_days=45, trial_price_override=50)
        agent = self._checkout('promo.paidtrial@example.com', 'free_trial', 'TRIAL45')
        sub = AgentSubscription.objects.get(agent=agent)
        paise = self._paise(sub)
        paid = {ORDER_A: [{'id': PAY_A, 'status': 'captured', 'amount': paise}]}
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(paise, paid)):
            self.assertTrue(verify_and_activate_pending_payment(agent))
        agent.refresh_from_db()
        self.assertGreater(agent.trial_ends_at, datetime.now() + timedelta(days=44))
        self.assertLess(agent.trial_ends_at, datetime.now() + timedelta(days=46))
