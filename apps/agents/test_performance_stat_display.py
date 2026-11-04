from django.test import SimpleTestCase

from apps.agents.models import AgentPerformanceStat
from apps.agents.services.display_format import format_success_rate_display


class PerformanceStatDisplayTests(SimpleTestCase):
    def test_success_rate_strips_existing_percent(self):
        self.assertEqual(format_success_rate_display("100.00%"), "100%")
        self.assertEqual(format_success_rate_display(100.0), "100%")

    def test_success_rate_fraction(self):
        self.assertEqual(format_success_rate_display(98.5), "98.5%")

    def test_effective_claims_settled_from_rate(self):
        stat = AgentPerformanceStat(
            claims_processed=75, claims_settled=0, success_rate="100.00%"
        )
        self.assertEqual(stat.effective_claims_settled, 75)
        self.assertEqual(stat.formatted_claims_settled, "75")
