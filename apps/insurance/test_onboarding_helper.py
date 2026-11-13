"""Characterisation of the three insurance onboarding paths (audit INS-S): the
single-agent form, the offline/approval cart and the paid bulk Razorpay order
must keep creating the same User / Agent / AgentProfile / AgentSubscription rows."""

import datetime
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.admin_panel.models.users import User as LaravelUser
from apps.agents.models import Agent, AgentSubscription
from apps.agents.services.feature_unlock import PLAN_LABELS
from apps.insurance.models import InsuranceBulkOrder, InsuranceProfile
from apps.insurance.views.agents import fulfil_insurance_bulk_order

ITEM = {
    "fullname": "Helper Agent",
    "email": "helper.agent@example.com",
    "mobile": "9000000777",
    "plan_type": "professional",
    "amount": 8258,
    "agent_pincode": "411001",
    "state": "MH",
}


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost"],
    RAZORPAY_KEY="rzp_test_k",
    RAZORPAY_SECRET="s",
)
class OnboardingHelperCharacterisationTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            "ins.helper", "ins.helper@example.com", "x"
        )
        InsuranceProfile.objects.create(user=self.manager, insurance_sub_role="manager")
        self.client.force_login(self.manager)

    def _rows(self, email=ITEM["email"]):
        user = User.objects.get(email=email)
        agent = Agent.objects.get(email=email)
        return user, agent, agent.profile, AgentSubscription.objects.get(agent=agent)

    def _assert_common(
        self, user, agent, profile, sub, pincode, state, plan_type="professional"
    ):
        self.assertEqual(user.username, user.email)
        self.assertTrue(
            user.check_password(user.email)
        )  # email-as-password (invariant 3 exception)
        self.assertFalse(user.is_active)
        self.assertEqual(agent.user, user)
        self.assertEqual(agent.insurance_id, self.manager.id)
        self.assertEqual(agent.onboarded_by, self.manager)
        self.assertEqual(agent.registration_step, 2)
        self.assertEqual(agent.plan_type, plan_type)
        self.assertEqual(profile.address, "Pincode: " + pincode)
        self.assertEqual(profile.state, state)
        self.assertEqual(sub.selected_plan, PLAN_LABELS[plan_type])
        self.assertEqual(sub.status, "inactive")
        self.assertTrue(LaravelUser.objects.filter(id=self.manager.id).exists())

    def test_agents_store(self):
        resp = self.client.post(
            reverse("insurance:agents_store"),
            {
                "fullname": "Store Agent",
                "email": "store.agent@example.com",
                "mobile": "9000000778",
                "plan_type": "starter",
                "agent_pincode": "400001",
                "state": "MH",
            },
        )
        self.assertRedirects(
            resp, reverse("insurance:agents_index"), fetch_redirect_response=False
        )
        user, agent, profile, sub = self._rows("store.agent@example.com")
        self._assert_common(
            user, agent, profile, sub, "400001", "MH", plan_type="starter"
        )
        self.assertEqual(agent.status, "pending_accounts_payment")
        self.assertEqual(agent.fullname, "Store Agent")
        self.assertEqual((agent.payment_method, agent.payment_reference), ("", ""))
        self.assertIsNone(agent.payment_recorded_at)
        self.assertIsNone(agent.payment_recorded_by)
        self.assertEqual(float(sub.registration_amount), 2359)
        self.assertEqual(sub.payment_status, "pending")
        self.assertTrue(sub.razorpay_order_id.startswith("INSURANCE_MANUAL_"))
        self.assertEqual(len(sub.razorpay_order_id), len("INSURANCE_MANUAL_") + 10)
        self.assertIsNone(sub.razorpay_payment_id)
        self.assertIsNone(sub.razorpay_signature)
        self.assertEqual((sub.expires_at - sub.starts_at).days, 365)
        self.assertLess(
            abs(sub.starts_at - datetime.datetime.now()), datetime.timedelta(minutes=1)
        )

    def test_agents_store_onboarding_role_needs_manager_approval(self):
        profile = InsuranceProfile.objects.get(user=self.manager)
        profile.insurance_sub_role = "onboarding"
        profile.save()
        self.client.post(
            reverse("insurance:agents_store"),
            {
                "fullname": "Ob Agent",
                "email": "ob.agent@example.com",
                "mobile": "9000000779",
                "plan_type": "professional",
                "agent_pincode": "400002",
                "state": "KA",
            },
        )
        user, agent, profile, sub = self._rows("ob.agent@example.com")
        self.assertEqual(agent.status, "pending_manager_approval")
        self.assertEqual(float(sub.registration_amount), 8258)

    def _cart(self, payment_type, **extra):
        session = self.client.session
        session["insurance_bulk_cart"] = [dict(ITEM)]
        session.save()
        return self.client.post(
            reverse("insurance:checkout_cart"), dict(payment_type=payment_type, **extra)
        )

    def test_checkout_cart_offline(self):
        paid_on = datetime.date.today() - datetime.timedelta(days=3)
        resp = self._cart(
            "offline",
            payment_method="NEFT",
            payment_reference="UTR987654321",
            payment_recorded_at=paid_on.isoformat(),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        user, agent, profile, sub = self._rows()
        self._assert_common(user, agent, profile, sub, "411001", "MH")
        recorded_at = datetime.datetime.combine(paid_on, datetime.time.min)
        self.assertEqual(agent.status, "pending_admin_approval")
        self.assertEqual(
            (agent.payment_method, agent.payment_reference), ("NEFT", "UTR987654321")
        )
        self.assertEqual(agent.payment_recorded_at, recorded_at)
        self.assertEqual(agent.payment_recorded_by, self.manager)
        self.assertEqual(float(sub.registration_amount), 8258)
        self.assertEqual(sub.payment_status, "completed")
        self.assertEqual(sub.starts_at, recorded_at)
        self.assertEqual(sub.expires_at, recorded_at + datetime.timedelta(days=365))
        self.assertTrue(sub.razorpay_order_id.startswith("OFFLINE_"))
        self.assertEqual(len(sub.razorpay_order_id), len("OFFLINE_") + 10)
        self.assertNotIn("UTR", sub.razorpay_order_id)
        self.assertIsNone(sub.razorpay_payment_id)
        self.assertNotIn("insurance_bulk_cart", self.client.session)

    def test_checkout_cart_approval(self):
        resp = self._cart("approval")
        self.assertEqual(resp.status_code, 200, resp.content)
        user, agent, profile, sub = self._rows()
        self._assert_common(user, agent, profile, sub, "411001", "MH")
        self.assertEqual(agent.status, "pending_manager_approval")
        self.assertEqual((agent.payment_method, agent.payment_reference), ("", ""))
        self.assertIsNone(agent.payment_recorded_at)
        self.assertIsNone(agent.payment_recorded_by)
        self.assertEqual(sub.payment_status, "pending")
        self.assertIsNone(sub.starts_at)
        self.assertIsNone(sub.expires_at)
        self.assertTrue(sub.razorpay_order_id.startswith("OFFLINE_"))

    def test_checkout_cart_duplicate_email_creates_nothing(self):
        User.objects.create_user("dupe", ITEM["email"], "x")
        resp = self._cart("approval")
        self.assertEqual(resp.status_code, 500)
        self.assertFalse(Agent.objects.filter(email=ITEM["email"]).exists())

    @mock.patch("apps.insurance.views.agents.razorpay")
    def test_fulfil_bulk_order(self, _rzp):
        LaravelUser.objects.get_or_create(
            id=self.manager.id,
            defaults={
                "fullname": "m",
                "email": self.manager.email,
                "password": "x",
                "role": "insurance",
                "status": "active",
            },
        )
        InsuranceBulkOrder.objects.create(
            razorpay_order_id="order_HELPER1",
            created_by=self.manager,
            company_id=self.manager.id,
            cart=[dict(ITEM)],
            amount_paise=825800,
        )
        payment = {
            "id": "pay_HELPER1",
            "order_id": "order_HELPER1",
            "amount": 825800,
            "status": "captured",
            "currency": "INR",
        }
        order, fulfilled = fulfil_insurance_bulk_order(
            "order_HELPER1", "pay_HELPER1", payment, "sig_helper"
        )
        self.assertTrue(fulfilled)
        self.assertEqual(order.status, "paid")
        user, agent, profile, sub = self._rows()
        self._assert_common(user, agent, profile, sub, "411001", "MH")
        self.assertEqual(agent.status, "pending_admin_approval")
        self.assertEqual((agent.payment_method, agent.payment_reference), ("", ""))
        self.assertIsNone(agent.payment_recorded_by)
        self.assertEqual(sub.payment_status, "completed")
        self.assertEqual(sub.razorpay_order_id, "order_HELPER1")
        self.assertEqual(sub.razorpay_payment_id, "pay_HELPER1")
        self.assertEqual(sub.razorpay_signature, "sig_helper")
        self.assertEqual((sub.expires_at - sub.starts_at).days, 365)
