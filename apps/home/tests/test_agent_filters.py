from django.test import SimpleTestCase

from apps.home.services.agent_filters import (
    canonicalize_product_tile,
    expand_product_db_names,
    is_others_product,
    map_insurance_types,
)


class InsuranceFilterMappingTests(SimpleTestCase):
    def test_homepage_fire_sme_selects_others(self):
        self.assertEqual(canonicalize_product_tile('Fire (SME)'), 'Others')
        self.assertTrue(is_others_product('Fire (SME)'))
        self.assertTrue(is_others_product('Others'))
        self.assertEqual(expand_product_db_names('Fire (SME)'), [])

    def test_sme_named_tiles_expand_to_stored_names(self):
        self.assertEqual(canonicalize_product_tile('Cyber (SME)'), 'Cyber')
        self.assertIn('GPA / GMC', expand_product_db_names('GPA/GMC'))
        self.assertIn('Fire', expand_product_db_names('Fire'))
        self.assertIn('Super Top-Up', expand_product_db_names('Top-up'))

    def test_insurance_type_aliases(self):
        self.assertEqual(map_insurance_types(['SME Insurance', 'Health']), ['sme', 'health'])
        self.assertEqual(map_insurance_types(['SME']), ['sme'])
        self.assertEqual(map_insurance_types(['Business Insurance']), ['sme'])
