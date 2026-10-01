"""Audit 2026-10-01 F-01: paying for an agent plan with a staff / insurance /
distributor email used to sign the payer into that account."""
from unittest.mock import patch

from django.contrib.auth.models import Group, User

from apps.admin_panel.models.users import User as LaravelUser
from apps.agents.models import Agent, AgentSubscription
from apps.agents.signup_test_support import ORDER_A, PAY_A, _SignupBase, _rzp
from apps.insurance.models import InsuranceProfile


class SignupPortalEmailTakeoverTests(_SignupBase):
    """F-01."""

    def _assert_step1_refused(self, email):
        r = self._step1(email)
        self.assertEqual(r.status_code, 422, r.content)
        self.assertFalse(r.json()['success'])
        self.assertFalse(Agent.objects.filter(email=email).exists())

    def test_superuser_email_refused_at_step1(self):
        User.objects.create_user('boss', 'boss@example.com', 'S3cret!!pw', is_staff=True, is_superuser=True)
        self._assert_step1_refused('boss@example.com')

    def test_insurance_portal_email_refused_at_step1(self):
        u = User.objects.create_user('insmgr', 'ins.manager@example.com', 'S3cret!!pw')
        InsuranceProfile.objects.create(user=u, insurance_sub_role='manager')
        self._assert_step1_refused('ins.manager@example.com')

    def test_distributor_group_email_refused_at_step1(self):
        u = User.objects.create_user('dist', 'dist@example.com', 'S3cret!!pw')
        u.groups.add(Group.objects.get_or_create(name='distributor')[0])
        self._assert_step1_refused('dist@example.com')

    def test_distributor_users_row_without_django_user_refused_at_step1(self):
        LaravelUser.objects.create(fullname='Dist', email='legacy.dist@example.com',
                                   password='$2y$10$x', role='distributor', status='active')
        self._assert_step1_refused('legacy.dist@example.com')

    def test_guest_client_email_can_still_register(self):
        User.objects.create_user('client1', 'client@example.com')  # passwordless client
        r = self._step1('client@example.com')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['success'])

    def test_unknown_legacy_users_role_keeps_previous_behaviour(self):
        """Only distributor/insurance/admin roles are portal roles; anything else behaves as before."""
        from apps.agents.services.account_auth import create_or_link_django_user
        LaravelUser.objects.create(fullname='Old', email='old.role@example.com',
                                   password='$2y$10$x', role='subagent', status='active')
        r = self._step1('old.role@example.com')
        self.assertEqual(r.status_code, 200, r.content)
        agent = Agent.objects.create(fullname='Old', email='old.role@example.com', mobile='9876543210')
        create_or_link_django_user(agent)
        self.assertEqual(LaravelUser.objects.get(email='old.role@example.com').role, 'agent')

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_payment_never_logs_in_staff_user_for_legacy_agent_row(self, _q):
        """Defence in depth: an agent row created before the step-1 guard."""
        staff = User.objects.create_user('boss2', 'boss2@example.com', 'S3cret!!pw', is_staff=True)
        agent = Agent.objects.create(fullname='X', email='boss2@example.com', mobile='9876543210',
                                     status='pending_payment', plan_type='starter')
        AgentSubscription.objects.create(agent=agent, selected_plan="Starter's Plan",
                                         registration_amount='1999.00', razorpay_order_id=ORDER_A)
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(199900)):
            r = self.client.post('/agent-register/verify-payment/', data={
                'razorpay_order_id': ORDER_A, 'razorpay_payment_id': PAY_A,
                'razorpay_signature': 'sig'}, content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(AgentSubscription.objects.get(razorpay_order_id=ORDER_A).payment_status, 'completed')
        self.assertNotEqual(str(self.client.session.get('_auth_user_id')), str(staff.pk))

    def test_linking_agent_keeps_distributor_users_role(self):
        from apps.agents.services.account_auth import create_or_link_django_user
        LaravelUser.objects.create(fullname='Dist', email='keep.role@example.com',
                                   password='$2y$10$abcdefghijklmnopqrstuuJ8Yt0mVfnG7m0lJ7cZ2Lr0oQnC0hq', role='distributor', status='active')
        agent = Agent.objects.create(fullname='X', email='keep.role@example.com', mobile='9876543210')
        create_or_link_django_user(agent)
        self.assertEqual(LaravelUser.objects.get(email='keep.role@example.com').role, 'distributor')

    @patch('apps.agents.views.registration.queue_invoice_and_welcome')
    def test_normal_signup_still_logs_payer_in(self, _q):
        agent = self._signup('normal.payer@example.com', [ORDER_A])
        sub = AgentSubscription.objects.get(razorpay_order_id=ORDER_A)
        with patch('apps.agents.views.registration.razorpay_client', return_value=_rzp(self._paise(sub))):
            r = self.client.post('/agent-register/verify-payment/', data={
                'razorpay_order_id': ORDER_A, 'razorpay_payment_id': PAY_A,
                'razorpay_signature': 'sig'}, content_type='application/json')
        self.assertTrue(r.json()['success'], r.json())
        agent.refresh_from_db()
        self.assertEqual(agent.status, 'pending_approval')
        self.assertEqual(str(self.client.session.get('_auth_user_id')), str(agent.user_id))
