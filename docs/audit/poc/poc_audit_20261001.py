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

    # F-01 and F-02 are fixed; their tests live in
    # apps/agents/test_signup_takeover_orphan_orders.py.

    # F-05 is fixed; see apps/referral_championship/test_referral_fixes_20261001.py.
    pass


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
