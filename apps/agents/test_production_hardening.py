import datetime
import importlib

from django.apps import apps as django_apps
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from apps.agents.models import Agent, AgentLead, AgentProfile, AgentProfileView
from apps.agents.services.google_review import track_google_review_click
from apps.home.models import GoogleReviewConfig, SiteSetting

merge_migration = importlib.import_module(
    "apps.agents.migrations.0040_agentprofileview_unique_agent_view_date"
)


class AgentProfileViewCounterTests(TestCase):
    def setUp(self):
        self.agent = Agent.objects.create(
            fullname="View Agent", email="view@test.com", mobile="9000000001"
        )

    def test_record_view_creates_then_increments_one_row(self):
        AgentProfileView.record_view(self.agent)
        AgentProfileView.record_view(self.agent)
        rows = AgentProfileView.objects.filter(
            agent=self.agent, view_date=datetime.date.today()
        )
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().view_count, 2)

    def test_migration_merges_duplicates_into_lowest_id(self):
        today = datetime.date.today()
        other = Agent.objects.create(
            fullname="Other", email="other@test.com", mobile="9000000002"
        )
        # Drop the unique index inside this test's transaction (SQLite DDL rolls back) to recreate legacy duplicates.
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(
                cursor, AgentProfileView._meta.db_table
            )
            index = next(
                name
                for name, c in constraints.items()
                if c["unique"] and c["columns"] == ["agent_id", "view_date"]
            )
            cursor.execute(f'DROP INDEX "{index}"')
        first = AgentProfileView.objects.create(
            agent=self.agent, view_date=today, view_count=3
        )
        AgentProfileView.objects.create(agent=self.agent, view_date=today, view_count=4)
        AgentProfileView.objects.create(agent=self.agent, view_date=today, view_count=1)
        single = AgentProfileView.objects.create(
            agent=other, view_date=today, view_count=5
        )

        merge_migration.merge_duplicate_profile_views(django_apps, None)

        rows = list(AgentProfileView.objects.filter(agent=self.agent))
        self.assertEqual([(r.pk, r.view_count) for r in rows], [(first.pk, 8)])
        single.refresh_from_db()
        self.assertEqual(single.view_count, 5)


class GoogleReviewClickCounterTests(TestCase):
    def test_click_is_an_atomic_increment(self):
        agent = Agent.objects.create(
            fullname="Review Agent", email="review@test.com", mobile="9000000003"
        )
        GoogleReviewConfig.objects.create(agent=agent, google_review_clicks=4)
        self.assertEqual(track_google_review_click(agent.id), 5)
        self.assertEqual(
            GoogleReviewConfig.objects.get(agent=agent).google_review_clicks, 5
        )


class CardLeadRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.agent = Agent.objects.create(
            fullname="Lead Agent",
            email="lead@test.com",
            mobile="9000000004",
            status="active",
            plan_type="professional",
        )
        AgentProfile.objects.create(
            agent=self.agent,
            slug="lead-agent",
            display_name="Lead Agent",
            is_profile_visible=True,
            is_card_visible=True,
        )
        SiteSetting.set_value("agent_digital_card_enabled", True, group="general")
        self.url = reverse(
            "agents:agent_card_lead_submit", kwargs={"slug": "lead-agent"}
        )

    def _post(self, i):
        return self.client.post(
            self.url,
            {
                "customer_name": "Ramesh Bhai",
                "customer_mobile": f"98989898{i:02d}",
                "insurance_type": "Health Insurance",
                "message": "Need a family floater plan",
            },
        )

    def test_sixth_enquiry_in_ten_minutes_gets_429(self):
        for i in range(5):
            self.assertEqual(self._post(i).status_code, 200, i)
        blocked = self._post(5)
        self.assertEqual(blocked.status_code, 429)
        self.assertFalse(blocked.json()["success"])
        self.assertEqual(AgentLead.objects.filter(agent=self.agent).count(), 5)
