import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.agents.models import Agent, AgentInsuranceSegment, AgentProfile
from apps.home.services.homepage_agents import _pick_top_per_segment


class HomepageSegmentLocationTests(TestCase):
    def test_home_without_location_uses_neutral_copy(self):
        response = self.client.get(reverse('home:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Meet the Right Expert Near')
        self.assertContains(response, '>you<')
        self.assertNotContains(response, 'Gulbai')
        self.assertEqual(response.context['home_location_label'], 'your area')
        self.assertEqual(response.context['segment_experts_mode'], 'placeholder')
        self.assertFalse(response.context['has_homepage_location'])

    def test_placeholder_renders_premium_showcase_services(self):
        response = self.client.get(reverse('home:home'))
        self.assertContains(response, 'Individual &amp; Family Health Plans')
        self.assertContains(response, 'Cashless Hospitalization')
        self.assertContains(response, 'Meet the Right Expert Near')


class SegmentCompareApiTests(TestCase):
    def test_compare_requires_location(self):
        res = self.client.get(reverse('home:segment_compare'), {'segment': 'health'})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.json()['success'])

    def test_compare_rejects_invalid_segment(self):
        session = self.client.session
        session['last_pincode'] = '380007'
        session.save()
        res = self.client.get(reverse('home:segment_compare'), {'segment': 'bogus'})
        self.assertEqual(res.status_code, 400)


class SegmentDedupeTests(TestCase):
    @patch('apps.home.services.homepage_agents.serialize_segment_agent', side_effect=lambda agent, key: {'id': agent.id})
    def test_pick_one_agent_per_segment_without_reuse(self, _serialize):
        def make_agent(aid, segments):
            agent = MagicMock()
            agent.id = aid
            agent.ordered_insurance_segments = segments
            agent.insuranceSegments = MagicMock()
            agent.insuranceSegments.all.return_value = [
                SimpleNamespace(segment_type=s) for s in segments
            ]
            agent.get_primary_profile = MagicMock(return_value=None)
            return agent

        agents = [
            make_agent(1, ['health', 'life']),
            make_agent(2, ['life', 'motor']),
            make_agent(3, ['motor', 'sme']),
            make_agent(4, ['sme', 'health']),
            make_agent(5, ['health']),
            make_agent(6, ['mutual_fund']),
        ]
        used = set()
        slots = _pick_top_per_segment(agents, used, per_segment=1)
        live_ids = [s['agent']['id'] for s in slots if s.get('agent')]
        self.assertEqual(len(live_ids), len(set(live_ids)))


class SegmentLiveModeTests(TestCase):
    def setUp(self):
        cache.clear()

    def _agent(self, name, slug, segment):
        agent = Agent.objects.create(
            fullname=name,
            email=f'{slug}@example.com',
            mobile='9876501234',
            status='active',
        )
        AgentProfile.objects.create(agent=agent, slug=slug, display_name=name, is_profile_visible=True)
        AgentInsuranceSegment.objects.create(agent=agent, segment_type=segment)
        return agent

    @patch('apps.home.views.pages._get_or_create_pincode')
    def test_home_with_pincode_enters_live_mode(self, lookup):
        lookup.return_value = SimpleNamespace(office_name='Paldi', district='Ahmedabad', latitude=23.01, longitude=72.56)
        self._agent('Health Only', 'health-only', 'health')
        payload = json.dumps({'pincode': '380007'})
        self.client.post(
            reverse('home:save_user_location'),
            data=payload,
            content_type='application/json',
        )
        response = self.client.get(reverse('home:home'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['has_homepage_location'])
        self.assertEqual(response.context['segment_experts_mode'], 'live')