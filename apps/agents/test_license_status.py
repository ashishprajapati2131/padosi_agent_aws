import datetime

from django.test import SimpleTestCase
from unittest.mock import MagicMock

from apps.agents.services.license_status import (
    compose_badge_csv,
    is_irdai_license_active,
    is_irdai_license_expired,
)


class LicenseStatusTests(SimpleTestCase):
    def test_active_without_expiry_date(self):
        profile = MagicMock(license_number="ABC123", license_valid_till=None)
        self.assertTrue(is_irdai_license_active(profile))
        self.assertFalse(is_irdai_license_expired(profile))

    def test_expired_license_hides_irdai_badge(self):
        profile = MagicMock(
            license_number="ABC123",
            license_valid_till=datetime.date(2020, 1, 1),
        )
        agent = MagicMock(badge="irdai,verified", profile=profile)
        self.assertTrue(is_irdai_license_expired(profile))
        self.assertEqual(compose_badge_csv(agent), "verified")
