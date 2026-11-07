"""Audit 2026-11-07 P6: pending registrations fetch light rows for all agents and full
rows (event/blacklist/review subqueries) only for the 25 on the current page."""
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from apps.agents.models import Agent
from apps.admin_panel.views import agents as agent_views


class PendingRegistrationsPagingTests(TestCase):
    def setUp(self):
        for i in range(30):
            Agent.objects.create(fullname=f"P{i}", email=f"p{i}@example.com", mobile=f"90000005{i:02d}",
                                 status="pending_payment")

    def _page(self, page):
        request = RequestFactory().get("/admin/agents/pending-registrations/", {"page": page})
        with patch.object(agent_views, "_get_admin_from_session", return_value=1), \
             patch.object(agent_views, "render", side_effect=lambda req, tpl, ctx: ctx):
            return agent_views.agent_pending_registrations(request)

    def test_page_has_full_rows_and_stats_cover_everything(self):
        ctx = self._page(1)
        self.assertEqual(ctx["totalPending"], 30)
        self.assertEqual(len(ctx["agents"]), 25)
        self.assertTrue(all("review_count" in a and "fullname" in a for a in ctx["agents"]))

    def test_second_page_gets_the_rest(self):
        first = {a["id"] for a in self._page(1)["agents"]}
        second = self._page(2)["agents"]
        self.assertEqual(len(second), 5)
        self.assertFalse(first & {a["id"] for a in second})
        self.assertTrue(all("fullname" in a for a in second))
