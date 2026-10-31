"""Insurance-portal Razorpay orders (single agent ``agent_ins_`` and bulk cart
``cart_ins_``) are fulfilled by the webhook / recovery as well as the browser
callback, exactly once, and only for a captured payment of the right amount."""

import json
from io import StringIO
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.agents.models import Agent, AgentSubscription
from apps.insurance.models import InsuranceBulkOrder, InsuranceProfile

SINGLE_ORDER = "order_INSSINGLE001"
SINGLE_PAY = "pay_INSSINGLE001"
SINGLE_PAISE = 235900
BULK_ORDER = "order_INSBULK001"
BULK_PAY = "pay_INSBULK001"
BULK_PAISE = 1061700  # 2359 + 8258 rupees
CART = [
    {
        "fullname": "Cart One",
        "email": "cart.one@example.com",
        "mobile": "9000000301",
        "plan_type": "starter",
        "amount": 2359,
        "agent_pincode": "400001",
        "state": "MH",
    },
    {
        "fullname": "Cart Two",
        "email": "cart.two@example.com",
        "mobile": "9000000302",
        "plan_type": "professional",
        "amount": 8258,
        "agent_pincode": "400002",
        "state": "MH",
    },
]


def _payment(pid, order_id, amount, status="captured"):
    return {
        "id": pid,
        "order_id": order_id,
        "amount": amount,
        "status": status,
        "currency": "INR",
    }


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost"],
    RAZORPAY_KEY="rzp_test_k",
    RAZORPAY_SECRET="s",
)
class InsuranceWebhookFulfilmentTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user("ins.whk", "ins.whk@example.com", "x")
        InsuranceProfile.objects.create(user=self.manager, insurance_sub_role="manager")
        self.agent = Agent.objects.create(
            fullname="Single",
            email="single.ins@example.com",
            mobile="9000000300",
            status="pending_accounts_payment",
            plan_type="starter",
            insurance_id=self.manager.id,
        )
        self.sub = AgentSubscription.objects.create(
            agent=self.agent,
            selected_plan="Starter's Plan",
            registration_amount="2359.00",
            payment_status="pending",
        )
        self.bulk = InsuranceBulkOrder.objects.create(
            razorpay_order_id=BULK_ORDER,
            created_by=self.manager,
            company_id=self.manager.id,
            cart=CART,
            amount_paise=BULK_PAISE,
        )
        self.orders = {
            SINGLE_ORDER: {
                "id": SINGLE_ORDER,
                "receipt": f"agent_ins_{self.agent.pk}_1",
                "amount": SINGLE_PAISE,
                "notes": {
                    "agent_id": self.agent.pk,
                    "insurance_user_id": self.manager.pk,
                },
            },
            BULK_ORDER: {
                "id": BULK_ORDER,
                "receipt": f"cart_ins_{self.manager.pk}_1",
                "amount": BULK_PAISE,
                "notes": {"insurance_user_id": self.manager.pk, "cart_size": 2},
            },
        }
        self.payments = {
            SINGLE_PAY: _payment(SINGLE_PAY, SINGLE_ORDER, SINGLE_PAISE),
            BULK_PAY: _payment(BULK_PAY, BULK_ORDER, BULK_PAISE),
        }
        self.rzp = MagicMock()
        self.rzp.order.fetch.side_effect = lambda oid: self.orders[oid]
        self.rzp.payment.fetch.side_effect = lambda pid: self.payments[pid]
        for target in (
            "apps.insurance.views.payments.razorpay",
            "apps.insurance.views.agents.razorpay",
        ):
            module = patch(target).start()
            module.Client.return_value = self.rzp
        patch(
            "apps.agents.views.registration.razorpay_client", return_value=self.rzp
        ).start()
        patch(
            "apps.agents.views.registration.razorpay_webhook_secret",
            return_value="whsec",
        ).start()
        self.addCleanup(patch.stopall)
        self.client.force_login(self.manager)

    def _webhook(self, payment):
        body = json.dumps(
            {"event": "payment.captured", "payload": {"payment": {"entity": payment}}}
        )
        return self.client.post(
            "/razorpay-webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE="sig",
        )

    def _single_browser(self):
        return self.client.post(
            reverse("insurance:handle_payment_success", args=[self.agent.pk]),
            {
                "razorpay_payment_id": SINGLE_PAY,
                "razorpay_order_id": SINGLE_ORDER,
                "razorpay_signature": "sig",
            },
        )

    def _bulk_browser(self):
        session = self.client.session
        session["insurance_bulk_cart"] = CART
        session["insurance_bulk_order_id"] = BULK_ORDER
        session.save()
        return self.client.post(
            reverse("insurance:checkout_online_success"),
            {
                "razorpay_payment_id": BULK_PAY,
                "razorpay_order_id": BULK_ORDER,
                "razorpay_signature": "sig",
            },
        )

    def _assert_single_paid(self):
        self.agent.refresh_from_db()
        self.sub.refresh_from_db()
        self.assertEqual(self.agent.status, "pending_admin_approval")
        self.assertEqual(
            (self.agent.payment_reference, self.agent.payment_recorded_by_id),
            (SINGLE_PAY, self.manager.pk),
        )
        self.assertEqual(
            (self.sub.payment_status, self.sub.razorpay_payment_id),
            ("completed", SINGLE_PAY),
        )
        self.assertIsNotNone(self.sub.expires_at)

    def _assert_bulk_paid(self):
        self.bulk.refresh_from_db()
        self.assertEqual(
            (self.bulk.status, self.bulk.razorpay_payment_id), ("paid", BULK_PAY)
        )
        for item in CART:
            self.assertEqual(Agent.objects.filter(email=item["email"]).count(), 1)
        subs = AgentSubscription.objects.filter(razorpay_order_id=BULK_ORDER)
        self.assertEqual(subs.count(), 2)
        self.assertTrue(
            all(
                s.payment_status == "completed" and s.razorpay_payment_id == BULK_PAY
                for s in subs
            )
        )
        self.assertEqual(
            Agent.objects.get(email=CART[0]["email"]).insurance_id, self.manager.id
        )

    # --- single agent -------------------------------------------------------
    def test_single_webhook_first_then_browser(self):
        self.assertEqual(self._webhook(self.payments[SINGLE_PAY]).status_code, 200)
        self._assert_single_paid()
        resp = self._single_browser()
        self.assertTrue(resp.json()["success"], resp.content)
        self._assert_single_paid()
        self.assertEqual(AgentSubscription.objects.filter(agent=self.agent).count(), 1)

    def test_single_browser_first_then_webhook(self):
        resp = self._single_browser()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIn("advanced to admin approval", resp.json()["message"])
        self._assert_single_paid()
        resp = self._webhook(self.payments[SINGLE_PAY])
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"already completed", resp.content)

    def test_single_browser_rejects_order_of_another_agent(self):
        other = Agent.objects.create(
            fullname="Other",
            email="other.ins@example.com",
            mobile="9000000309",
            status="pending_accounts_payment",
            insurance_id=self.manager.id,
        )
        resp = self.client.post(
            reverse("insurance:handle_payment_success", args=[other.pk]),
            {
                "razorpay_payment_id": SINGLE_PAY,
                "razorpay_order_id": SINGLE_ORDER,
                "razorpay_signature": "sig",
            },
        )
        self.assertEqual(resp.status_code, 400)
        other.refresh_from_db()
        self.agent.refresh_from_db()
        self.assertEqual(
            (other.status, self.agent.status),
            ("pending_accounts_payment", "pending_accounts_payment"),
        )

    def test_single_amount_mismatch_is_acked_and_not_fulfilled(self):
        self.assertEqual(
            self._webhook(_payment(SINGLE_PAY, SINGLE_ORDER, 100)).status_code, 200
        )
        self.agent.refresh_from_db()
        self.sub.refresh_from_db()
        self.assertEqual(
            (self.agent.status, self.sub.payment_status),
            ("pending_accounts_payment", "pending"),
        )

    def test_single_uncaptured_payment_is_not_fulfilled(self):
        self.assertEqual(
            self._webhook(
                _payment(SINGLE_PAY, SINGLE_ORDER, SINGLE_PAISE, "failed")
            ).status_code,
            200,
        )
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, "pending_accounts_payment")

    def test_unexpected_error_returns_500_for_retry(self):
        with patch(
            "apps.insurance.views.payments._complete_insurance_agent_payment",
            side_effect=RuntimeError("db"),
        ):
            self.assertEqual(self._webhook(self.payments[SINGLE_PAY]).status_code, 500)

    # --- bulk cart ----------------------------------------------------------
    def test_bulk_webhook_first_then_browser(self):
        self.assertEqual(self._webhook(self.payments[BULK_PAY]).status_code, 200)
        self._assert_bulk_paid()
        resp = self._bulk_browser()
        self.assertTrue(resp.json()["success"], resp.content)
        self._assert_bulk_paid()
        self.assertNotIn("insurance_bulk_cart", self.client.session)

    def test_bulk_browser_first_then_webhook(self):
        resp = self._bulk_browser()
        self.assertTrue(resp.json()["success"], resp.content)
        self._assert_bulk_paid()
        resp = self._webhook(self.payments[BULK_PAY])
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"already completed", resp.content)
        self._assert_bulk_paid()

    def test_bulk_amount_mismatch_is_acked_and_not_fulfilled(self):
        self.assertEqual(
            self._webhook(_payment(BULK_PAY, BULK_ORDER, 100)).status_code, 200
        )
        self.bulk.refresh_from_db()
        self.assertEqual(self.bulk.status, "pending")
        self.assertFalse(Agent.objects.filter(email=CART[0]["email"]).exists())

    def test_bulk_uncaptured_payment_is_not_fulfilled(self):
        self.assertEqual(
            self._webhook(
                _payment(BULK_PAY, BULK_ORDER, BULK_PAISE, "failed")
            ).status_code,
            200,
        )
        self.bulk.refresh_from_db()
        self.assertEqual(self.bulk.status, "pending")
        self.assertFalse(Agent.objects.filter(email=CART[0]["email"]).exists())

    def test_bulk_already_registered_email_marks_order_failed(self):
        User.objects.create_user("taken", CART[1]["email"], "x")
        self.assertEqual(self._webhook(self.payments[BULK_PAY]).status_code, 200)
        self.bulk.refresh_from_db()
        self.assertEqual(
            (self.bulk.status, self.bulk.razorpay_payment_id), ("failed", BULK_PAY)
        )
        self.assertIn("already registered", self.bulk.error)
        self.assertFalse(
            Agent.objects.filter(email=CART[0]["email"]).exists()
        )  # rolled back

    def test_bulk_start_stores_cart_on_the_order_row(self):
        self.rzp.order.create.return_value = {"id": "order_INSBULKNEW"}
        session = self.client.session
        session["insurance_bulk_cart"] = CART
        session.save()
        resp = self.client.post(reverse("insurance:checkout_online_start"))
        self.assertEqual(resp.status_code, 200, resp.content)
        row = InsuranceBulkOrder.objects.get(razorpay_order_id="order_INSBULKNEW")
        self.assertEqual(
            (row.cart, row.amount_paise, row.created_by_id, row.status),
            (CART, BULK_PAISE, self.manager.pk, "pending"),
        )

    # --- recovery -----------------------------------------------------------
    def test_recover_command_fulfils_orphaned_insurance_orders(self):
        self.rzp.payment.all.return_value = {
            "items": [self.payments[SINGLE_PAY], self.payments[BULK_PAY]]
        }
        out = StringIO()
        with patch(
            "apps.agents.services.razorpay_checkout.razorpay_client",
            return_value=self.rzp,
        ):
            call_command("recover_orphaned_payments", "--days", "7", stdout=out)
            self.assertIn("INSURANCE_AGENT_NOT_FULFILLED", out.getvalue())
            self.assertIn("INSURANCE_BULK_NOT_FULFILLED", out.getvalue())
            self.agent.refresh_from_db()
            self.assertEqual(self.agent.status, "pending_accounts_payment")  # dry run

            call_command(
                "recover_orphaned_payments", "--days", "7", "--apply", stdout=out
            )
        self._assert_single_paid()
        self._assert_bulk_paid()

        out = StringIO()
        with patch(
            "apps.agents.services.razorpay_checkout.razorpay_client",
            return_value=self.rzp,
        ):
            call_command("recover_orphaned_payments", "--days", "7", stdout=out)
        self.assertNotIn("INSURANCE_", out.getvalue())
