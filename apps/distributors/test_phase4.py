"""Audit phase 4: INS16 (invite message never creates a users row), INS19
(agents list paginated in the DB, same rows/order; dashboard stats aggregate)."""

import datetime
import json

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.admin_panel.models import User as LaravelUser
from apps.agents.models import Agent, AgentDraft


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class DistributorPhase4Tests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("p4d@example.com", "p4d@example.com", "x")
        self.user.groups.add(Group.objects.get_or_create(name="distributor")[0])
        self.client.force_login(self.user)

    def _post_invite(self):
        return self.client.post(
            reverse("distributors:dashboard_invite_message"),
            json.dumps({"custom_invite_message": "hi"}),
            content_type="application/json",
        )

    def test_invite_message_without_users_row_is_404(self):
        resp = self._post_invite()
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(LaravelUser.objects.filter(email="p4d@example.com").exists())

    def test_invite_message_saved_for_existing_row(self):
        row = LaravelUser.objects.create(
            fullname="P4",
            email="p4d@example.com",
            password="x",
            role="distributor",
            status="active",
        )
        self.assertEqual(self._post_invite().status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.custom_invite_message, "hi")

    def test_agents_index_merges_agents_and_drafts_across_pages(self):
        dist = LaravelUser.objects.create(
            fullname="P4",
            email="p4d@example.com",
            password="x",
            role="distributor",
            status="active",
        )
        base = timezone.now()
        expected = []
        for i in range(8):
            a = Agent.objects.create(
                fullname=f"A{i}",
                email=f"a{i}@p4.com",
                mobile=f"90000004{i:02d}",
                status="active",
                distributor_id=dist.id,
            )
            Agent.objects.filter(pk=a.pk).update(
                created_at=base - datetime.timedelta(hours=2 * i)
            )
            expected.append(f"A{i}")
            d = AgentDraft.objects.create(
                session_key=f"s{i}",
                email=f"d{i}@p4.com",
                fullname=f"D{i}",
                registration_step=1,
                distributor_id=dist.id,
            )
            AgentDraft.objects.filter(pk=d.pk).update(
                created_at=base - datetime.timedelta(hours=2 * i + 1)
            )
            expected.append(f"D{i}")
        # Draft for an email that already is an agent stays hidden.
        AgentDraft.objects.create(
            session_key="dup",
            email="a0@p4.com",
            fullname="DUP",
            registration_step=1,
            distributor_id=dist.id,
        )

        seen = []
        for page in (1, 2):
            resp = self.client.get(reverse("distributors:agents_index"), {"page": page})
            self.assertEqual(resp.status_code, 200)
            page_obj = resp.context["agents"]
            self.assertEqual(page_obj.paginator.count, 16)
            seen += [a.fullname for a in page_obj]
        self.assertEqual(seen, expected)

        resp = self.client.get(reverse("distributors:dashboard"))
        self.assertEqual(resp.status_code, 200)
