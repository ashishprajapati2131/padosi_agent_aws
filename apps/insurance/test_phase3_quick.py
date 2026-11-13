"""Audit phase 3 quick fixes: INS4 (approve/reject only pending agents),
INS14 (no exception text to clients), INS15 (role + action checks)."""

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.agents.models import Agent
from apps.insurance.models import InsuranceProfile


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class InsurancePhase3Tests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user("p3.mgr", "p3.mgr@example.com", "x")
        InsuranceProfile.objects.create(user=self.manager, insurance_sub_role="manager")
        self.agent = Agent.objects.create(
            fullname="P3",
            email="p3agent@example.com",
            mobile="9000000301",
            status="active",
            insurance_id=self.manager.id,
        )

    def _user(self, role):
        u = User.objects.create_user(f"p3.{role}", f"p3.{role}@example.com", "x")
        # Same company as the manager (sub-users resolve to the parent company id).
        InsuranceProfile.objects.create(
            user=u, insurance_sub_role=role, insurance_parent=self.manager
        )
        return u

    def test_approve_and_reject_ignore_non_pending_agent(self):
        self.client.force_login(self.manager)
        self.client.post(reverse("insurance:approvals_approve", args=[self.agent.pk]))
        self.client.post(
            reverse("insurance:approvals_reject", args=[self.agent.pk]),
            {"rejection_reason": "no"},
        )
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, "active")

    def test_approve_pending_agent_still_works(self):
        Agent.objects.filter(pk=self.agent.pk).update(status="pending_manager_approval")
        self.client.force_login(self.manager)
        self.client.post(reverse("insurance:approvals_approve", args=[self.agent.pk]))
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, "pending_accounts_payment")

    def test_record_payment_error_hides_exception_text(self):
        Agent.objects.filter(pk=self.agent.pk).update(status="pending_accounts_payment")
        self.client.force_login(self.manager)
        with patch(
            "apps.agents.models.Agent.save",
            side_effect=RuntimeError("SECRET-DB-DETAIL"),
        ):
            resp = self.client.post(
                reverse("insurance:record_payment", args=[self.agent.pk]),
                {
                    "payment_method": "neft",
                    "payment_reference": "UTR1",
                    "payment_recorded_at": "2024-01-01",
                },
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn("SECRET-DB-DETAIL", resp.content.decode())

    def _status_change(self, action):
        # agent_approval_requests is unmanaged (no test table): mock the model.
        with patch("apps.insurance.views.agents.AgentApprovalRequest") as model:
            model.objects.filter.return_value.exists.return_value = False
            self.client.post(
                reverse("insurance:request_status_change", args=[self.agent.pk]),
                {"action": action, "reason": "x"},
            )
        return model.objects.create

    def test_status_change_rejects_unknown_action(self):
        self.client.force_login(self.manager)
        self.assertFalse(self._status_change("delete_everything").called)
        self.assertTrue(self._status_change("deactivate").called)

    def test_status_change_and_notify_need_role(self):
        self.client.force_login(self._user("accounts"))
        self.assertFalse(self._status_change("deactivate").called)
        resp = self.client.post(
            reverse("insurance:notify_send"),
            {"agent_id": self.agent.pk, "title": "t", "body": "b"},
        )
        self.assertEqual(resp.status_code, 403)


class RejectionReasonKeptTests(TestCase):  # audit INS4 (reason part)
    def test_reason_is_appended_to_admin_notes(self):
        from django.contrib.auth.models import User

        from apps.agents.models import Agent
        from apps.insurance.models import InsuranceProfile

        mgr = User.objects.create_user('mgr4', 'mgr4@example.com', 'pw')
        prof = InsuranceProfile.objects.create(user=mgr, insurance_sub_role='manager')
        company_id = prof.get_insurance_company_id()
        agent = Agent.objects.create(fullname='Pending', email='p4@example.com', mobile='9876500411',
                                     status='pending_manager_approval', insurance_id=company_id,
                                     admin_notes='earlier note')
        self.client.force_login(mgr)
        from django.urls import reverse
        self.client.post(reverse('insurance:approvals_reject', args=[agent.pk]),
                         {'rejection_reason': 'Licence expired'})
        agent.refresh_from_db()
        self.assertEqual(agent.status, 'rejected')
        self.assertIn('earlier note', agent.admin_notes)
        self.assertIn('Licence expired', agent.admin_notes)
