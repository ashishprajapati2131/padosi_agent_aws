import datetime

from django.test import SimpleTestCase
from unittest.mock import MagicMock

from apps.agents.services.licensed_badge import insurance_license_badge_visible


class LicensedBadgeVisibilityTests(SimpleTestCase):
    def _agent(self, badge="", license_number="", valid_till=None):
        agent = MagicMock()
        agent.badge = badge
        profile = MagicMock()
        profile.license_number = license_number
        profile.license_valid_till = valid_till
        agent.profile = profile
        return agent

    def test_irdai_flag_with_valid_date(self):
        future = datetime.date.today() + datetime.timedelta(days=30)
        agent = self._agent(badge="irdai", valid_till=future)
        self.assertTrue(insurance_license_badge_visible(agent))

    def test_irdai_flag_expired_hidden(self):
        past = datetime.date.today() - datetime.timedelta(days=1)
        agent = self._agent(badge="irdai", license_number="LIC123", valid_till=past)
        self.assertFalse(insurance_license_badge_visible(agent))

    def test_license_number_without_flag_shown(self):
        agent = self._agent(badge="verified", license_number="LIC999")
        self.assertTrue(insurance_license_badge_visible(agent))

    def test_no_credential(self):
        agent = self._agent(badge="verified")
        self.assertFalse(insurance_license_badge_visible(agent))

    def test_og_share_respects_expiry(self):
        from apps.agents.services.og_image import _card_data

        past = datetime.date.today() - datetime.timedelta(days=2)
        agent = self._agent(badge="irdai", license_number="X1", valid_till=past)
        self.assertFalse(_card_data(agent)['show_licensed'])
