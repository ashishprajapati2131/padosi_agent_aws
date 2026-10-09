from django.test import SimpleTestCase

from apps.agents.services.feature_unlock import (
    PLAN_LABELS,
    resolve_agent_display_plan_label,
)


class PlanDisplaySyncTests(SimpleTestCase):
    def test_plan_type_wins_over_stale_free_subscription(self):
        label = resolve_agent_display_plan_label(
            'professional',
            'Free Trial',
        )
        self.assertEqual(label, PLAN_LABELS['professional'])

    def test_basic_grant_shows_starter_label(self):
        label = resolve_agent_display_plan_label('basic', '')
        self.assertEqual(label, PLAN_LABELS['starter'])
