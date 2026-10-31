"""Saving a pincode from the location popup must not crash (resolve_home_location was undefined)."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse


class SaveLocationPincodeTests(TestCase):
    def post(self, payload):
        return self.client.post(reverse('home:save_user_location'), data=json.dumps(payload), content_type='application/json')

    @patch('apps.home.views.pages._get_or_create_pincode')
    def test_known_pincode_saves_area_and_coordinates(self, lookup):
        lookup.return_value = SimpleNamespace(office_name='Paldi', district='Ahmedabad', latitude=23.01, longitude=72.56)
        res = self.post({'pincode': '380007'})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body['detected_area'], 'Paldi')
        self.assertEqual(body['city_label'], 'Ahmedabad')
        session = self.client.session
        self.assertEqual(session['last_pincode'], '380007')
        self.assertEqual(session['last_lat'], '23.01')
        self.assertEqual(session['last_lng'], '72.56')

    @patch('apps.home.views.pages._get_or_create_pincode', return_value=None)
    def test_unknown_pincode_falls_back_to_the_pincode(self, lookup):
        res = self.post({'pincode': '380007'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['detected_area'], '380007')
        self.assertEqual(res.json()['city_label'], '380007')
        self.assertNotIn('last_lat', self.client.session)

    @patch('apps.home.views.pages._get_or_create_pincode', side_effect=RuntimeError('db down'))
    def test_lookup_error_still_saves_the_pincode(self, lookup):
        res = self.post({'pincode': '380007'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.client.session['last_pincode'], '380007')
