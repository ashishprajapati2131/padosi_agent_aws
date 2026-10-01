"""Proof-of-concept tests for the 2026-10-01 audit (NOT part of the repo).

Each test asserts the CORRECT behaviour. A FAIL means the bug is present.
Run from the project root:
    PYTHONPATH=<this dir> DEBUG=True python manage.py test poc_audit_20261001 --noinput
Razorpay is mocked at the gateway boundary, like apps/agents/test_registration_e2e.py.
"""
import json
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.agents.models import Agent, AgentSubscription
from apps.home.models import SiteSetting
from apps.home.models.pincode import Pincode

ORDER_A = 'order_POCAAAAAAAAAA1'
ORDER_B = 'order_POCBBBBBBBBBB2'
PAY_A = 'pay_POCAAAAAAAAAAA1'


def _rzp(amount_paise):
    c = MagicMock()
    c.utility.verify_payment_signature.return_value = True
    c.utility.verify_webhook_signature.return_value = True
    c.payment.fetch.return_value = {'status': 'captured', 'amount': amount_paise}
    c.order.payments.return_value = {'items': []}
    return c


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'], RAZORPAY_WEBHOOK_SECRET='whsec_test')
class RegistrationPaymentPoC(TestCase):
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

    def _signup_until_order(self, email, order_ids):
        r = self.client.post('/agent-register-step1/', {
            'fullname': 'Poc Agent', 'email': email, 'mobile': '9876543210',
            'agent_pincode': '380001', 'state': 'Gujarat', 'experience_range': '5',
            'segments[]': ['life'],
        })
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['success'], r.json())
        self.client.post('/agent-register-step2/', {'bio': 'x'})
        self.client.get('/chooseplan/')
        for oid in order_ids:
            with patch('apps.agents.views.registration.create_checkout_order', return_value=(oid, False)):
                rr = self.client.post('/agent-register/complete/', data={'plan_type': 'starter'},
                                      content_type='application/json')
            self.assertEqual(rr.status_code, 200, rr.content)

    # ── F-01 (CRITICAL) ────────────────────────────────────────────────────
    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_F01_signup_with_staff_email_must_not_log_in_as_staff(self, _q):
        staff = User.objects.create_user('boss', 'boss@padosi-test.com', 'S3cret!!pw', is_staff=True, is_superuser=True)
        self._signup_until_order('boss@padosi-test.com', [ORDER_A])
        sub = AgentSubscription.objects.get(razorpay_order_id=ORDER_A)
        paise = int(round(float(sub.registration_amount) * 100))
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(paise)):
            self.client.post('/agent-register/verify-payment/', data={
                'razorpay_order_id': ORDER_A, 'razorpay_payment_id': PAY_A,
                'razorpay_signature': 'sig'}, content_type='application/json')
        session_uid = self.client.session.get('_auth_user_id')
        self.assertNotEqual(str(session_uid), str(staff.pk),
                            'Payer was logged in as the pre-existing SUPERUSER that owns this email')

    # ── F-02 (CRITICAL) ────────────────────────────────────────────────────
    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_F02_paid_first_order_after_retry_must_activate(self, _q):
        """User opens checkout (order A), closes modal, clicks Pay again (order B),
        then approves A in the UPI app. Razorpay captures A and sends the webhook."""
        self._signup_until_order('retry.payer@padosi-test.com', [ORDER_A, ORDER_B])
        agent = Agent.objects.get(email='retry.payer@padosi-test.com')
        sub = AgentSubscription.objects.filter(agent=agent).order_by('-created_at').first()
        paise = int(round(float(sub.registration_amount) * 100))
        body = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': {
            'id': PAY_A, 'order_id': ORDER_A, 'amount': paise, 'status': 'captured'}}}})
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(paise)), \
             patch('apps.agents.views.registration.razorpay_webhook_secret', return_value='whsec_test'):
            r = self.client.post('/razorpay-webhook/', data=body, content_type='application/json',
                                 HTTP_X_RAZORPAY_SIGNATURE='sig')
        agent.refresh_from_db()
        paid = AgentSubscription.objects.filter(agent=agent, payment_status='completed').exists()
        self.assertTrue(paid, f'Captured order A was never activated (webhook HTTP {r.status_code}, '
                              f'agent status={agent.status}); money taken, agent missing from Approvals')

    # ── F-05 (HIGH) ────────────────────────────────────────────────────────
    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_F05_webhook_activation_must_run_championship_and_event_hooks(self, _q):
        self._signup_until_order('webhook.first@padosi-test.com', [ORDER_A])
        sub = AgentSubscription.objects.get(razorpay_order_id=ORDER_A)
        paise = int(round(float(sub.registration_amount) * 100))
        body = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': {
            'id': PAY_A, 'order_id': ORDER_A, 'amount': paise, 'status': 'captured'}}}})
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(paise)), \
             patch('apps.agents.views.registration.razorpay_webhook_secret', return_value='whsec_test'), \
             patch('apps.agents.views.registration._championship_qualification') as champ, \
             patch('apps.agents.views.registration._event_referral_qualification') as evt:
            r = self.client.post('/razorpay-webhook/', data=body, content_type='application/json',
                                 HTTP_X_RAZORPAY_SIGNATURE='sig')
        self.assertEqual(r.status_code, 200, r.content)
        sub.refresh_from_db()
        self.assertEqual(sub.payment_status, 'completed')
        self.assertTrue(champ.called and evt.called,
                        f'webhook path skipped referral hooks: championship={champ.called} event={evt.called}')


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class EventFunnelPoC(TestCase):
    def test_F13_event_register_post_is_routed_to_register_view(self):
        """events:register.submit and register.form share 'register/'; POST hits show_form."""
        from django.urls import resolve
        match = resolve('/events/register/')
        self.assertEqual(match.func.__name__, 'register',
                         f"POST /events/register/ is dispatched to {match.func.__name__}() - the "
                         f"register view is unreachable")


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class UpgradePoC(TestCase):
    def test_F10_upgrade_with_promo_code_must_not_crash(self):
        from apps.agents.views import dashboard as d
        try:
            import importlib
            importlib.import_module('apps.admin_panel.models.promo_code')
            ok = True
        except ImportError:
            ok = False
        self.assertTrue(ok, 'agent_upgrade_plan imports apps.admin_panel.models.promo_code, '
                            'which does not exist -> every upgrade with a promo code errors')


class FastApiPasswordPoC(TestCase):
    def test_F07_sqlalchemy_agent_user_fk_targets_same_table_as_django(self):
        from fastapi_app.models.agent import Agent as SAAgent
        fk = list(SAAgent.__table__.c.user_id.foreign_keys)[0].target_fullname
        from apps.agents.models import Agent as DjAgent
        dj_target = DjAgent._meta.get_field('user').related_model._meta.db_table
        self.assertEqual(fk.split('.')[0], dj_target,
                         f'agents.user_id holds {dj_target}.id (Django) but FastAPI joins it to {fk}; '
                         f'in-app password change writes a different person\'s users row')
