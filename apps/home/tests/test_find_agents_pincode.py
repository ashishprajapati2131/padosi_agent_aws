from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.urls import resolve

from apps.home.services.distance import (
    DistanceService,
    agent_serves_pincode,
    apply_search_proximity,
    iter_agent_service_pincodes,
)


class FakeRelated:
    def __init__(self, rows=None):
        self._rows = rows or []

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


def make_agent(**kwargs):
    profile_pins = kwargs.pop('profile_pins', None)
    table_pins = kwargs.pop('table_pins', None)
    agent = SimpleNamespace(
        agent_pincode=kwargs.get('agent_pincode', ''),
        latitude=kwargs.get('latitude'),
        longitude=kwargs.get('longitude'),
        profile=SimpleNamespace(service_pincodes=profile_pins) if profile_pins is not None else None,
        servicePincodes=FakeRelated([
            SimpleNamespace(service_pincode=pin) for pin in (table_pins or [])
        ]),
        serviceableCities=FakeRelated([]),
    )
    return agent


class AgentPincodeMatchTests(SimpleTestCase):
    def test_matches_json_dict_list(self):
        agent = make_agent(profile_pins=[{'pincode': '384285', 'area': 'Unjha'}])
        self.assertTrue(agent_serves_pincode(agent, '384285'))
        self.assertEqual(iter_agent_service_pincodes(agent), ['384285'])

    def test_matches_agent_pincode_and_service_table(self):
        agent = make_agent(agent_pincode='384001', table_pins=['384285'])
        self.assertTrue(agent_serves_pincode(agent, '384285'))
        self.assertTrue(agent_serves_pincode(agent, '384001'))
        self.assertFalse(agent_serves_pincode(agent, '380001'))


class SearchProximityTests(SimpleTestCase):
    def test_exact_service_pin_is_kept_outside_50km(self):
        # Ahmedabad coords vs Patan-area agent GPS (~125km)
        agent = make_agent(
            profile_pins=['384285'],
            latitude=23.85,
            longitude=72.12,
        )
        kept = apply_search_proximity(
            [agent],
            user_lat=23.0225,
            user_lng=72.5714,
            search_pincode='384285',
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].distance, 0)
        self.assertTrue(kept[0].serves_search_pincode)

    def test_far_agent_without_pin_is_dropped(self):
        agent = make_agent(
            profile_pins=['110001'],
            latitude=28.6139,
            longitude=77.2090,
        )
        kept = apply_search_proximity(
            [agent],
            user_lat=23.0225,
            user_lng=72.5714,
            search_pincode='384285',
        )
        self.assertEqual(kept, [])


class PincodeCoordinateLookupTests(SimpleTestCase):
    def test_database_coords_win_over_ahmedabad_prefix(self):
        record = MagicMock()
        record.latitude = 23.803
        record.longitude = 72.391
        with patch('apps.home.services.distance.Pincode.objects') as qs:
            qs.filter.return_value.first.return_value = record
            coords = DistanceService.get_pincode_coordinates('384285')
        self.assertAlmostEqual(coords['lat'], 23.803)
        self.assertAlmostEqual(coords['lng'], 72.391)


class ReviewUrlOrderTests(SimpleTestCase):
    def test_profile_review_is_not_captured_as_state_slug(self):
        match = resolve('/profile/ashish-prajapati/review/')
        self.assertEqual(match.url_name, 'agent_store_review')
        self.assertEqual(match.kwargs.get('slug'), 'ashish-prajapati')
        self.assertNotIn('state_code', match.kwargs)
