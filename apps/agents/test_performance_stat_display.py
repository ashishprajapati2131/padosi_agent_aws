from decimal import Decimal

from django.test import SimpleTestCase

from apps.agents.models import AgentPerformanceStat
from apps.agents.services.display_format import (
    format_success_rate_display,
    parse_claims_amount,
    parse_claims_count,
)


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

    def test_parse_claims_amount_from_varchar(self):
        self.assertEqual(parse_claims_amount("7645454656"), Decimal("7645454656"))
        self.assertEqual(parse_claims_amount("₹7,645,454,656"), Decimal("7645454656"))
        self.assertEqual(parse_claims_amount(""), Decimal("0"))
        self.assertEqual(parse_claims_amount(None), Decimal("0"))

    def test_parse_claims_count_from_varchar(self):
        self.assertEqual(parse_claims_count("160"), 160)
        self.assertEqual(parse_claims_count("155"), 155)
        self.assertEqual(parse_claims_count(""), 0)

    def test_has_claims_amount_when_db_returns_string(self):
        # Live DB columns are varchar; Django may surface str values.
        stat = AgentPerformanceStat(
            claims_processed="160",
            claims_settled="155",
            claims_amount="7645454656",
            success_rate="96.880",
        )
        self.assertTrue(stat.has_claims_amount)
        self.assertEqual(stat.numeric_claims_amount, Decimal("7645454656"))
        self.assertEqual(stat.formatted_claims_amount, "764.55 Cr")
        self.assertEqual(stat.effective_claims_settled, 155)
        self.assertEqual(stat.formatted_claims_processed, "160")

    def test_has_claims_amount_false_when_empty(self):
        stat = AgentPerformanceStat(claims_amount="0")
        self.assertFalse(stat.has_claims_amount)
        self.assertEqual(stat.formatted_claims_amount, "0")
