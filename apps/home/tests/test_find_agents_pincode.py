from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.urls import resolve

from django.core.paginator import Paginator

from apps.home.services.distance import (
    FIND_AGENTS_PAGE_SIZE,
    DistanceService,
    agent_serves_pincode,
    apply_search_proximity,
    iter_agent_service_pincodes,
    rank_directory_agents,
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

    def test_far_agent_kept_when_requested(self):
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
            keep_outside_radius=True,
        )
        self.assertEqual(len(kept), 1)
        self.assertFalse(kept[0].is_nearby)


class DirectoryRankingTests(SimpleTestCase):
    def test_nearby_search_only_returns_within_radius(self):
        nearby = make_agent(profile_pins=['384285'], latitude=23.85, longitude=72.12)
        far = make_agent(profile_pins=['110001'], latitude=28.6139, longitude=77.2090)
        ranked = rank_directory_agents(
            [nearby, far],
            user_lat=23.0225,
            user_lng=72.5714,
            search_pincode='384285',
        )
        self.assertEqual(len(ranked), 1)
        self.assertTrue(ranked[0].is_nearby)
        self.assertEqual(ranked[0], nearby)

    def test_no_location_keeps_all_agents(self):
        nearby = make_agent(profile_pins=['384285'], latitude=23.85, longitude=72.12)
        far = make_agent(profile_pins=['110001'], latitude=28.6139, longitude=77.2090)
        ranked = rank_directory_agents(
            [nearby, far],
            user_lat=None,
            user_lng=None,
            search_pincode=None,
        )
        self.assertEqual(len(ranked), 2)

    def test_no_nearby_agents_stays_empty(self):
        far = make_agent(profile_pins=['110001'], latitude=28.6139, longitude=77.2090)
        ranked = rank_directory_agents(
            [far],
            user_lat=23.0225,
            user_lng=72.5714,
            search_pincode='384285',
        )
        self.assertEqual(ranked, [])

    def test_first_page_is_five_and_has_next(self):
        agents = [object() for _ in range(8)]
        paginator = Paginator(agents, FIND_AGENTS_PAGE_SIZE)
        page = paginator.page(1)
        self.assertEqual(len(page.object_list), 5)
        self.assertTrue(page.has_next())
        self.assertEqual(page.next_page_number(), 2)


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

    def test_precise_pincode_coordinates(self):
        self.assertIsNotNone(DistanceService.get_precise_pincode_coordinates('380001'))
        self.assertIsNone(DistanceService.get_precise_pincode_coordinates('389999'))

    def test_is_regional_fallback_coordinate(self):
        fallback = DistanceService.get_regional_fallback_coordinates('389999')
        self.assertTrue(DistanceService.is_regional_fallback_coordinate('389999', fallback['lat'], fallback['lng']))
        self.assertFalse(DistanceService.is_regional_fallback_coordinate('389999', 28.6139, 77.2090))
        # Exact pin 380001 is never a fallback
        self.assertFalse(DistanceService.is_regional_fallback_coordinate('380001', 23.0225, 72.5714))


class ReviewUrlOrderTests(SimpleTestCase):
    def test_profile_review_is_not_captured_as_state_slug(self):
        match = resolve('/profile/ashish-prajapati/review/')
        self.assertEqual(match.url_name, 'agent_store_review')
        self.assertEqual(match.kwargs.get('slug'), 'ashish-prajapati')
        self.assertNotIn('state_code', match.kwargs)
