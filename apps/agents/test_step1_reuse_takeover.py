"""Step 1 needs no login, so a stranger re-using an unpaid registration by email must not be able
to change its mobile (the first password once the order is paid; audit PAY1)."""
from unittest.mock import patch


from apps.agents.models import Agent
from apps.agents.signup_test_support import _SignupBase

NO_GATEWAY = patch(
    'apps.agents.views.registration.verify_and_activate_pending_payment', return_value=False
)


class Step1ReuseTakeoverTests(_SignupBase):
    def setUp(self):
        super().setUp()
        self.victim = Agent.objects.create(
            fullname='Victim', email='victim@example.com', mobile='9812345678',
            status='pending_payment', plan_type='starter',
        )

    @NO_GATEWAY
    def test_stranger_with_other_mobile_is_refused(self, _v):
        r = self._step1('victim@example.com', mobile='9900990099')
        self.assertEqual(r.status_code, 422, r.content)
        self.victim.refresh_from_db()
        self.assertEqual(self.victim.mobile, '9812345678')

    @NO_GATEWAY
    def test_returning_owner_with_same_mobile_can_continue(self, _v):
        r = self._step1('victim@example.com', mobile='9812345678')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['success'])

    @NO_GATEWAY
    def test_session_that_owns_checkout_may_change_mobile(self, _v):
        session = self.client.session
        session['pending_checkout'] = {'agent_id': self.victim.pk}
        session.save()
        r = self._step1('victim@example.com', mobile='9900990099')
        self.assertEqual(r.status_code, 200, r.content)
        self.victim.refresh_from_db()
        self.assertEqual(self.victim.mobile, '9900990099')
