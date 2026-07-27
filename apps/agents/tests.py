from django.test import TestCase
from django.urls import reverse
from apps.agents.models import Agent, AgentProfile, AgentPerformanceStat
from django.core.cache import cache

class AgentSharingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = Agent.objects.create(
            fullname="Anil Paul Dabhi",
            email="anil.dabhi@padosiagent.com",
            mobile="9876543210",
            status="active"
        )
        self.profile = AgentProfile.objects.create(
            agent=self.agent,
            slug="anil-paul-dabhi",
            display_name="Anil Paul Dabhi",
            experience_years=12,
            license_number="IRDAI12345678",
            arn_number="AMFI987654",
            is_profile_visible=True
        )
        self.perf = AgentPerformanceStat.objects.create(
            agent=self.agent,
            claims_settled=150,
            claims_processed=160
        )

    def test_public_share_profile_view_active(self):
        response = self.client.get(reverse('agents:agent_public_share_profile', args=['anil-paul-dabhi']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anil Paul Dabhi")
        self.assertContains(response, "IRDAI Licensed")
        self.assertContains(response, "AMFI Registered")
        self.assertContains(response, "12+ Yrs")
        self.assertContains(response, "150+")

    def test_public_share_profile_view_inactive(self):
        self.profile.is_profile_visible = False
        self.profile.save()
        
        response = self.client.get(reverse('agents:agent_public_share_profile', args=['anil-paul-dabhi']))
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, 'agents/profile_unavailable.html')
        self.assertContains(response, "Profile Not Available", status_code=404)

    def test_og_image_generator(self):
        response = self.client.get(reverse('agents:agent_og_image', args=[self.agent.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')

        # Check caching
        cache_key = f'og_image_agent_card_{self.agent.id}'
        self.assertTrue(cache.get(cache_key) is not None)

        # Check invalidation signal works
        self.profile.experience_years = 15
        self.profile.save()
        self.assertTrue(cache.get(cache_key) is None)
