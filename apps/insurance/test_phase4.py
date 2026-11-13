"""Audit phase 4 INS19: agents/payments lists paginate (25/page); manager and
onboarding dashboard stats come from one aggregate with the same numbers."""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.agents.models import Agent
from apps.insurance.models import InsuranceProfile


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class InsurancePhase4Tests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user("p4.mgr", "p4.mgr@example.com", "x")
        InsuranceProfile.objects.create(user=self.manager, insurance_sub_role="manager")
        statuses = (
            ["active"] * 20 + ["inactive"] * 3 + ["pending_accounts_payment"] * 27
        )
        for i, status in enumerate(statuses):
            Agent.objects.create(
                fullname=f"P4 {i}",
                email=f"p4a{i}@example.com",
                mobile=f"90000{i:05d}",
                status=status,
                insurance_id=self.manager.id,
            )
        self.client.force_login(self.manager)

    def test_agents_list_paginates(self):
        resp = self.client.get(reverse("insurance:agents_index"))
        self.assertEqual(len(resp.context["agents"]), 25)
        self.assertEqual(resp.context["agents"].paginator.num_pages, 2)
        resp = self.client.get(reverse("insurance:agents_index"), {"page": 2})
        self.assertEqual(len(resp.context["agents"]), 25)

    def test_payments_list_paginates(self):
        resp = self.client.get(reverse("insurance:payments_index"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["agents"]), 25)
        resp = self.client.get(reverse("insurance:payments_index"), {"page": 2})
        self.assertEqual(len(resp.context["agents"]), 2)

    @patch("apps.insurance.views.dashboard.AgentApprovalRequest")
    def test_manager_dashboard_counts(self, approval_model):
        # agent_approval_requests is unmanaged (no table in the test DB).
        approval_model.objects.filter.return_value.count.return_value = 0
        ctx = self.client.get(reverse("insurance:dashboard")).context
        self.assertEqual(ctx["totalAgents"], 50)
        self.assertEqual(ctx["activeAgents"], 20)
        self.assertEqual(ctx["inactiveAgents"], 3)
        self.assertEqual(ctx["newAgentsThisMonth"], 50)
        self.assertEqual(ctx["trendData"][-1], 50)
        self.assertEqual(sum(ctx["trendData"]), 50)
        self.assertEqual(len(ctx["trendLabels"]), 6)

    def test_onboarding_dashboard_counts(self):
        ob = User.objects.create_user("p4.ob", "p4.ob@example.com", "x")
        InsuranceProfile.objects.create(
            user=ob, insurance_sub_role="onboarding", insurance_parent=self.manager
        )
        Agent.objects.filter(status="inactive").update(onboarded_by=ob.id)
        self.client.force_login(ob)
        ctx = self.client.get(reverse("insurance:dashboard")).context
        self.assertEqual(ctx["totalOnboardedByMe"], 3)
        self.assertEqual(ctx["activeAgents"], 0)
        self.assertEqual(ctx["pendingPayment"], 0)
