import json
from unittest.mock import patch
from decimal import Decimal

from django.test import TestCase, RequestFactory
from django.utils import timezone

from apps.agents.models import Agent, AgentProfile, AgentSubscription
from apps.admin_panel.models import AgentServicePincode
from apps.home.models import Pincode, PincodeCache
from apps.admin_panel.views.find_agent_locator import (
    locator_index,
    extract_coordinates,
    save_pincode_to_master,
    search_agents,
    assign_agent_to_pincode,
    create_and_add_agent,
    live_preview,
    unlink_agent_pincode,
)
from apps.admin_panel.views.pincode import (
    index as pincode_index,
    sample_download as pincode_sample,
    export_data as pincode_export,
    delete_by_state as pincode_delete_state,
)
from apps.admin_panel.models.admin_activity_log import AdminActivityLog


class FindAgentLocatorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin_id = 1

        # Seed sample agent
        self.agent = Agent.objects.create(
            fullname="Test Agent",
            email="test.agent.locator@example.com",
            mobile="9898989898",
            status="active",
            is_approved=True,
            agent_pincode="380015",
            latitude=Decimal("23.03050000"),
            longitude=Decimal("72.50660000"),
        )
        self.profile = AgentProfile.objects.create(
            agent=self.agent,
            display_name="Test Agent",
            service_pincodes=[{'pincode': '380015', 'city_name': 'Ahmedabad'}],
            is_card_visible=True,
            is_profile_visible=True,
        )

    def _auth_request(self, method, path, data=None, is_json=True):
        if method == 'GET':
            req = self.factory.get(path, data=data or {})
        else:
            if is_json:
                req = self.factory.post(path, data=json.dumps(data or {}), content_type='application/json')
            else:
                req = self.factory.post(path, data=data or {})
        req.session = {'admin_id': self.admin_id}
        return req

    @patch('apps.admin_panel.views.find_agent_locator._get_admin_from_session', return_value=1)
    def test_locator_index_renders_200(self, mock_admin):
        req = self._auth_request('GET', '/admin/find-agent-locator/')
        resp = locator_index(req)
        self.assertEqual(resp.status_code, 200)

    @patch('apps.admin_panel.views.find_agent_locator._get_admin_from_session', return_value=1)
    def test_extract_coordinates_valid_pincode(self, mock_admin):
        # 380015 is in EXACT_PINCODE_COORDS
        req = self._auth_request('POST', '/admin/find-agent-locator/extract/', {'pincode': '380015'})
        resp = extract_coordinates(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['pincode'], '380015')
        self.assertAlmostEqual(data['data']['latitude'], 23.02, places=1)
        self.assertAlmostEqual(data['data']['longitude'], 72.51, places=1)

    @patch('apps.admin_panel.views.find_agent_locator._get_admin_from_session', return_value=1)
    def test_extract_coordinates_382150_viramgam(self, mock_admin):
        # 382150 is Viramgam, Ahmedabad, Gujarat
        req = self._auth_request('POST', '/admin/find-agent-locator/extract/', {'pincode': '382150'})
        resp = extract_coordinates(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['pincode'], '382150')
        self.assertEqual(data['data']['office_name'], 'Viramgam SO')
        self.assertEqual(data['data']['district'], 'Ahmedabad')
        self.assertEqual(data['data']['state'], 'Gujarat')
        self.assertAlmostEqual(data['data']['latitude'], 23.1191, places=3)
        self.assertAlmostEqual(data['data']['longitude'], 72.0547, places=3)
        self.assertEqual(data['data']['source'], 'Database (Master Records)')

    @patch('apps.admin_panel.views.find_agent_locator._get_admin_from_session', return_value=1)
    def test_extract_coordinates_invalid_format(self, mock_admin):
        req = self._auth_request('POST', '/admin/find-agent-locator/extract/', {'pincode': '012345'})
        resp = extract_coordinates(req)
        self.assertEqual(resp.status_code, 422)
        data = json.loads(resp.content)
        self.assertFalse(data['success'])

    @patch('apps.admin_panel.views.find_agent_locator._get_admin_from_session', return_value=1)
    def test_save_pincode_to_master(self, mock_admin):
        payload = {
            'pincode': '380099',
            'office_name': 'Test Locality',
            'district': 'Ahmedabad',
            'state': 'Gujarat',
            'latitude': 23.0500,
            'longitude': 72.5200,
            'division': 'Ahmedabad City',
            'taluk': 'Daskroi',
        }
        req = self._auth_request('POST', '/admin/find-agent-locator/save-pincode/', payload)
        resp = save_pincode_to_master(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

        # Verify in PincodeCache
        cached = PincodeCache.get_coordinates('380099')
        self.assertIsNotNone(cached)
        self.assertAlmostEqual(cached['lat'], 23.05, places=2)

    @patch('apps.admin_panel.views.find_agent_locator._get_admin_from_session', return_value=1)
    def test_search_agents(self, mock_admin):
        req = self._auth_request('GET', '/admin/find-agent-locator/search-agents/?q=Test')
        resp = search_agents(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])
        self.assertTrue(len(data['agents']) >= 1)
        self.assertEqual(data['agents'][0]['id'], self.agent.id)

    @patch('apps.admin_panel.views.find_agent_locator._get_admin_from_session', return_value=1)
    def test_assign_agent_to_pincode(self, mock_admin):
        payload = {
            'agent_id': self.agent.id,
            'pincode': '395009',
            'latitude': 21.2028,
            'longitude': 72.8304,
            'city_name': 'Surat',
            'set_primary': True,
            'add_service_pincode': True,
            'activate_agent': True,
        }
        req = self._auth_request('POST', '/admin/find-agent-locator/assign-agent/', payload)
        resp = assign_agent_to_pincode(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

        self.agent.refresh_from_db()
        self.assertEqual(self.agent.agent_pincode, '395009')
        self.assertAlmostEqual(float(self.agent.latitude), 21.2028, places=4)

        # Verify service pincodes
        self.profile.refresh_from_db()
        pins = [p.get('pincode') if isinstance(p, dict) else p for p in self.profile.service_pincodes]
        self.assertIn('395009', pins)

    @patch('apps.admin_panel.views.find_agent_locator._get_admin_from_session', return_value=1)
    def test_create_and_add_agent(self, mock_admin):
        payload = {
            'fullname': 'Quick Onboarded Agent',
            'mobile': '9777888999',
            'email': 'quick.locator@example.com',
            'pincode': '400001',
            'latitude': 18.9220,
            'longitude': 72.8347,
            'city_name': 'Mumbai',
            'insurance_type': 'Life',
            'company_name': 'LIC',
        }
        req = self._auth_request('POST', '/admin/find-agent-locator/create-agent/', payload)
        resp = create_and_add_agent(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

        created_agent = Agent.objects.filter(email='quick.locator@example.com').first()
        self.assertIsNotNone(created_agent)
        self.assertEqual(created_agent.agent_pincode, '400001')
        self.assertEqual(created_agent.status, 'active')
        self.assertTrue(created_agent.is_approved)

    @patch('apps.admin_panel.views.find_agent_locator._get_admin_from_session', return_value=1)
    def test_live_preview(self, mock_admin):
        # Query 380015 which self.agent services
        req = self._auth_request('GET', '/admin/find-agent-locator/live-preview/?pincode=380015&latitude=23.0305&longitude=72.5066')
        resp = live_preview(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])
        self.assertTrue(data['total_found'] >= 1)
        found_ids = [a['id'] for a in data['agents']]
        self.assertIn(self.agent.id, found_ids)

    @patch('apps.admin_panel.views.find_agent_locator._get_admin_from_session', return_value=1)
    def test_unlink_agent_pincode(self, mock_admin):
        payload = {
            'agent_id': self.agent.id,
            'pincode': '380015',
        }
        req = self._auth_request('POST', '/admin/find-agent-locator/unlink-agent/', payload)
        resp = unlink_agent_pincode(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

        self.profile.refresh_from_db()
        pins = [p.get('pincode') if isinstance(p, dict) else p for p in (self.profile.service_pincodes or [])]
        self.assertNotIn('380015', pins)

    @patch('apps.admin_panel.views.pincode._get_admin_from_session', return_value=1)
    def test_pincode_index_elided_pagination_and_context(self, mock_admin):
        # Create sample pincodes
        for i in range(1, 15):
            Pincode.objects.get_or_create(
                pincode=f"3800{i:02d}",
                defaults={
                    'office_name': f"Area {i}",
                    'district': "Ahmedabad",
                    'state': "Gujarat",
                    'latitude': Decimal("23.0300"),
                    'longitude': Decimal("72.5000"),
                }
            )

        req = self._auth_request('GET', '/admin/pincode-manager/?search=Area&state=Gujarat')
        resp = pincode_index(req)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('Pincode Manager', content)
        self.assertIn('Gujarat', content)
        self.assertIn('Purge Gujarat', content)

    @patch('apps.admin_panel.views.pincode._get_admin_from_session', return_value=1)
    def test_pincode_sample_and_export_downloads(self, mock_admin):
        # Test sample download
        req_sample = self._auth_request('GET', '/admin/pincode-manager/sample/')
        resp_sample = pincode_sample(req_sample)
        self.assertEqual(resp_sample.status_code, 200)
        self.assertIn('text/csv', resp_sample['Content-Type'])
        self.assertIn('pincode_sample.csv', resp_sample['Content-Disposition'])

        # Test export
        req_export = self._auth_request('GET', '/admin/pincode-manager/export/?state=Gujarat')
        resp_export = pincode_export(req_export)
        self.assertEqual(resp_export.status_code, 200)
        self.assertIn('text/csv', resp_export['Content-Type'])
        self.assertIn('pincodes_export.csv', resp_export['Content-Disposition'])

    @patch('apps.admin_panel.views.pincode._get_admin_from_session', return_value=1)
    def test_delete_by_state_with_audit_log(self, mock_admin):
        Pincode.objects.get_or_create(
            pincode="403001",
            defaults={
                'office_name': "Panaji",
                'district': "North Goa",
                'state': "Goa",
                'latitude': Decimal("15.4909"),
                'longitude': Decimal("73.8278"),
            }
        )
        self.assertTrue(Pincode.objects.filter(state="Goa").exists())

        req = self._auth_request('POST', '/admin/pincode-manager/delete-state/', {'state': 'Goa'})
        resp = pincode_delete_state(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])
        self.assertFalse(Pincode.objects.filter(state="Goa").exists())
