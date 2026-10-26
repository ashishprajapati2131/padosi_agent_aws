from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.agents.models import Agent, AgentProfile


class LicensedWordingTests(TestCase):
    """'Licensed' is only claimed when the agent has entered a license number."""

    def _profile(self, slug, license_number):
        agent = Agent.objects.create(fullname='Test Agent', email=f'{slug}@example.com', mobile='9876501234', status='active')
        AgentProfile.objects.create(agent=agent, slug=slug, display_name='Test Agent',
                                    is_profile_visible=True, license_number=license_number)
        return self.client.get(reverse('agents:agent_public_profile', args=[slug]))

    def setUp(self):
        cache.clear()

    def test_without_license_number_no_licensed_claim(self):
        response = self._profile('no-license', '')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Agent, an Insurance &amp; Financial Advisor')
        self.assertContains(response, '"description": "Insurance and Financial Advisor on PadosiAgent"')
        self.assertNotContains(response, 'a Licensed Insurance')

    def test_with_license_number_says_licensed(self):
        response = self._profile('has-license', 'IRDAI12345678')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Agent, a Licensed Insurance &amp; Financial Advisor')
        self.assertContains(response, '"description": "Licensed Insurance and Financial Advisor on PadosiAgent"')
