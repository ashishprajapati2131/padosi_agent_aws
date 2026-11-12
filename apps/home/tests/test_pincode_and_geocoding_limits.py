"""Public pincode / geocoding endpoints trigger external calls, so they need rate limits
and must never let random coordinates fan out to Nominatim (audit WEB3/4)."""
import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.home.models import Pincode


class PincodeFetchLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        Pincode.objects.create(
            pincode='380001', office_name='Ahmedabad GPO', district='Ahmedabad',
            state='Gujarat', latitude='23.0', longitude='72.5',
        )

    @override_settings(REST_FRAMEWORK={})
    def test_cap_returns_429_after_many_hits(self):
        url = reverse('home:pincode_fetch', args=['380001'])
        last = None
        for _ in range(35):
            last = self.client.get(url)
        self.assertEqual(last.status_code, 429)

    def test_office_name_is_never_overwritten_by_reverse_geocode(self):
        with patch(
            'apps.home.services.geocoding.GeocodingService.resolve_coordinates',
            return_value={'display_name': 'something very long from Nominatim'},
        ):
            self.client.get(reverse('home:pincode_fetch', args=['380001']))
        self.assertEqual(Pincode.objects.get(pincode='380001').office_name, 'Ahmedabad GPO')


class SaveLocationRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def _post(self, lat, lng):
        return self.client.post(
            reverse('home:save_user_location'),
            data=json.dumps({'lat': str(lat), 'lng': str(lng)}),
            content_type='application/json',
        )

    @patch('apps.home.views.pages.GeocodingService')
    def test_out_of_india_does_not_call_nominatim(self, geo):
        self._post(40.7, -74.0)
        geo.assert_not_called()

    @patch('apps.home.views.pages.GeocodingService')
    def test_second_call_within_a_minute_is_skipped(self, geo):
        geo.return_value.reverse_geocode.return_value = 'Paldi'
        self._post(23.0, 72.5)
        self._post(23.1, 72.6)
        self.assertEqual(geo.return_value.reverse_geocode.call_count, 1)

    @patch('apps.home.views.pages.GeocodingService')
    def test_nan_rejected(self, geo):
        self._post('nan', 'nan')
        geo.assert_not_called()
