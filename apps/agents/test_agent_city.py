from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from apps.agents.models import Agent, AgentProfile, City
from apps.agents.services.agent_city import resolve_agent_city
from apps.agents.services.og_image import _share_card_place


class AgentCityResolutionTests(TestCase):
    def _agent(self, name, pin, address, *cities, state='Gujarat'):
        agent = Agent.objects.create(
            fullname=name,
            email=f'{pin or name}@city.test',
            mobile='9000000000',
            status='active',
            agent_pincode=pin,
        )
        AgentProfile.objects.create(
            agent=agent,
            display_name=name,
            address=address,
            state=state,
            service_pincodes=[pin] if pin else [],
        )
        for city_name in cities:
            city, _ = City.objects.get_or_create(name=city_name, defaults={'slug': city_name.lower()})
            agent.serviceableCities.add(city)
        return agent

    def test_pincode_city_beats_ahmedabad_service_city(self):
        agent = self._agent(
            'Parth', '384240', 'Nana, Patan, Gujarat, India',
            'Ahmedabad', 'Ajmer', 'patan',
        )
        row = SimpleNamespace(office_name='Harij Taluka, Patan', district='', state='Gujarat')
        with patch('apps.home.models.pincode.Pincode') as pin_model:
            pin_model.objects.filter.return_value.first.return_value = row
            self.assertEqual(resolve_agent_city(agent), 'Patan')
            self.assertEqual(_share_card_place(agent), 'Patan, India')

    def test_address_city_when_pincode_row_is_placeholder(self):
        agent = self._agent(
            'Joy', '383001', 'Nayaymandir, himatnagar383001',
            'Ahmedabad', 'himmatnagar', 'baroda',
        )
        row = SimpleNamespace(office_name='Area 383001', district='Region 38', state='Gujarat')
        with patch('apps.home.models.pincode.Pincode') as pin_model:
            pin_model.objects.filter.return_value.first.return_value = row
            self.assertEqual(resolve_agent_city(agent), 'Himmatnagar')

    def test_single_real_service_city_is_used(self):
        agent = self._agent('Upasana', '360005', 'Rajkot', 'Rajkot')
        row = SimpleNamespace(office_name='Area 360005', district='Region 36', state='Gujarat')
        with patch('apps.home.models.pincode.Pincode') as pin_model:
            pin_model.objects.filter.return_value.first.return_value = row
            self.assertEqual(resolve_agent_city(agent), 'Rajkot')

    def test_unknown_city_uses_state_not_ahmedabad(self):
        agent = self._agent('Viral', '394163', '', state='Gujarat')
        row = SimpleNamespace(office_name='Area 394163', district='Region 39', state='Gujarat')
        with patch('apps.home.models.pincode.Pincode') as pin_model:
            pin_model.objects.filter.return_value.first.return_value = row
            self.assertEqual(resolve_agent_city(agent), 'Gujarat')
            self.assertNotIn('Ahmedabad', _share_card_place(agent))
