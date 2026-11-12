"""Suspended / deleted / unpaid agents have no public profile, reviews, leads or OG image (audit AG3)."""
from django.test import TestCase
from django.urls import reverse

from apps.agents.models import Agent, AgentProfile


class HiddenAgentPublicViewsTests(TestCase):
    def _agent(self, status):
        agent = Agent.objects.create(
            fullname='Hidden', email=f'{status}@example.com', mobile='9000000909', status=status
        )
        AgentProfile.objects.create(agent=agent, slug=f'hidden-{status}')
        return agent

    def test_suspended_agent_pages_404(self):
        agent = self._agent('suspended')
        slug = agent.profile.slug
        self.assertEqual(self.client.get(reverse('agents:agent_public_profile', args=[slug])).status_code, 404)
        self.assertEqual(
            self.client.post(reverse('agents:agent_store_review', args=[slug]), {'rating': 5}).status_code, 404
        )
        self.assertEqual(
            self.client.post(reverse('agents:agent_leads_capture'), {'agent_id': agent.pk, 'interaction_type': 'call'}).status_code,
            404,
        )
        self.assertEqual(self.client.get(f'/og-image/{agent.pk}/og.jpg').status_code, 404)

    def test_active_agent_profile_still_opens(self):
        agent = self._agent('active')
        r = self.client.get(reverse('agents:agent_public_profile', args=[agent.profile.slug]))
        self.assertEqual(r.status_code, 200)

    def test_owner_still_sees_own_suspended_profile(self):
        from django.contrib.auth.models import User

        agent = self._agent('suspended')
        agent.user = User.objects.create_user('own@example.com', 'own@example.com', 'x')
        agent.save(update_fields=['user'])
        self.client.force_login(agent.user)
        r = self.client.get(reverse('agents:agent_public_profile', args=[agent.profile.slug]))
        self.assertEqual(r.status_code, 200)
