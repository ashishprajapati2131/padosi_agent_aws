"""380009 must show its Head Post Office (Navrangpura), not a taluka mashup."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.home.services.geocoding import (
    GeocodingService,
    office_label_unusable,
    row_needs_postal_refresh,
)

OFFICES_380009 = [
    {
        'Name': 'Ashram Road',
        'BranchType': 'Sub Post Office',
        'DeliveryStatus': 'Non-Delivery',
        'Block': 'City Ahmedabad',
        'District': 'Ahmedabad',
        'State': 'Gujarat',
        'Division': 'Ahmedabad City',
    },
    {
        'Name': 'Darpan Society',
        'BranchType': 'Sub Post Office',
        'DeliveryStatus': 'Non-Delivery',
        'Block': 'City Taluka',
        'District': 'Ahmedabad',
        'State': 'Gujarat',
        'Division': 'Ahmedabad City',
    },
    {
        'Name': 'Gujarat University',
        'BranchType': 'Sub Post Office',
        'DeliveryStatus': 'Non-Delivery',
        'Block': 'Ahmadabad City',
        'District': 'Ahmedabad',
        'State': 'Gujarat',
        'Division': 'Ahmedabad City',
    },
    {
        'Name': 'Navrangpura',
        'BranchType': 'Head Post Office',
        'DeliveryStatus': 'Delivery',
        'Block': 'Ahmadabad City',
        'District': 'Ahmedabad',
        'State': 'Gujarat',
        'Division': 'Ahmedabad City',
    },
]


class HeadOfficeLabelTests(SimpleTestCase):
    def test_picker_returns_navrangpura_not_an_earlier_branch(self):
        picked = GeocodingService._pick_best_post_office(OFFICES_380009)
        self.assertEqual(picked['Name'], 'Navrangpura')

    def test_label_is_the_head_office_name_not_the_block(self):
        label = GeocodingService.postal_place_label(OFFICES_380009[-1])
        self.assertEqual(label, 'Navrangpura, Ahmedabad')
        self.assertNotIn('Taluka', label)
        self.assertNotIn('Ahmadabad City', label)

    def test_postal_lookup_geocodes_the_head_office_name(self):
        queries = []

        def side_effect(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if 'postalpincode' in url:
                resp.json.return_value = [{'Status': 'Success', 'PostOffice': OFFICES_380009}]
            else:
                queries.append(kwargs['params']['q'])
                resp.json.return_value = [{'lat': '23.0368', 'lon': '72.5611'}]
            return resp

        with patch('apps.home.services.geocoding.requests.get', side_effect=side_effect):
            result = GeocodingService().call_postal_pincode_api('380009')

        self.assertEqual(result['display_name'], 'Navrangpura, Ahmedabad')
        self.assertEqual(result['office_name'], 'Navrangpura')
        self.assertTrue(queries[0].startswith('Navrangpura, Ahmedabad'))

    def test_mashed_taluka_row_needs_refresh(self):
        row = SimpleNamespace(
            pincode='380009',
            office_name='SabarmatiTaluka, Ahmedabad',
            district='',
            latitude=Decimal('23.0225'),
            longitude=Decimal('72.5714'),
        )
        self.assertTrue(office_label_unusable(row.office_name))
        self.assertTrue(row_needs_postal_refresh(row))

    def test_real_office_is_left_alone(self):
        row = SimpleNamespace(
            pincode='395003',
            office_name='Athwa',
            district='Surat',
            latitude=Decimal('21.1702'),
            longitude=Decimal('72.8311'),
        )
        self.assertFalse(office_label_unusable(row.office_name))
        self.assertFalse(row_needs_postal_refresh(row))
        self.assertFalse(office_label_unusable('Anand Taluka'))


class RefreshStoredPincodeTests(SimpleTestCase):
    @patch('apps.home.views.pincode.cache')
    @patch('apps.home.models.PincodeCache.store_coordinates')
    @patch('apps.home.views.pincode.http_requests.get')
    @patch('apps.home.services.geocoding.GeocodingService.geocode_place_name')
    def test_bad_380009_row_is_saved_as_navrangpura(self, geocode, http_get, store, cache):
        from apps.home.views.pincode import _get_or_create_pincode
        from apps.home.views import pincode as pincode_view

        existing = SimpleNamespace(
            pincode='380009',
            office_name='SabarmatiTaluka, Ahmedabad',
            district='',
            latitude=Decimal('23.0225'),
            longitude=Decimal('72.5714'),
        )
        cache.add.return_value = True
        geocode.return_value = {'lat': 23.0368, 'lng': 72.5611}
        http_get.return_value.raise_for_status.return_value = None
        http_get.return_value.json.return_value = [
            {'Status': 'Success', 'PostOffice': OFFICES_380009}
        ]
        saved = SimpleNamespace(
            office_name='Navrangpura',
            district='Ahmedabad',
            formatted_location='Navrangpura, Ahmedabad',
        )

        with patch.object(pincode_view.Pincode.objects, 'filter') as filt, \
                patch.object(pincode_view.Pincode.objects, 'update_or_create') as upsert:
            filt.return_value.first.return_value = existing
            upsert.return_value = (saved, True)
            record = _get_or_create_pincode('380009')

        self.assertIs(record, saved)
        defaults = upsert.call_args.kwargs['defaults']
        self.assertEqual(defaults['office_name'], 'Navrangpura')
        self.assertEqual(defaults['district'], 'Ahmedabad')
        self.assertEqual(defaults['latitude'], 23.0368)
        self.assertNotIn('Taluka', defaults['office_name'])
        geocode.assert_called_once_with('Navrangpura', 'Ahmedabad', 'Gujarat')
        store.assert_called_once()
        self.assertEqual(store.call_args.args[3], 'Navrangpura, Ahmedabad')

    @patch('apps.home.views.pincode.http_requests.get')
    def test_healthy_row_is_not_refetched(self, http_get):
        from apps.home.views.pincode import _get_or_create_pincode
        from apps.home.views import pincode as pincode_view

        existing = SimpleNamespace(
            pincode='395003',
            office_name='Athwa',
            district='Surat',
            latitude=Decimal('21.1702'),
            longitude=Decimal('72.8311'),
        )
        with patch.object(pincode_view.Pincode.objects, 'filter') as filt:
            filt.return_value.first.return_value = existing
            record = _get_or_create_pincode('395003')

        self.assertIs(record, existing)
        http_get.assert_not_called()
