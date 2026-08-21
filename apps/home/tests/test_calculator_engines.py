from django.test import SimpleTestCase

from apps.home.calculators.engines import (
    calculate,
    sip,
    goal_sip,
    lumpsum,
    emi,
    compound_interest,
    inflation,
    ppf,
    human_life_value,
    insurance_premium,
    step_up_sip,
    gratuity,
    gst,
    income_tax,
    bond_yield,
    bmi_calculator,
    idv_calculator,
    section_80d,
    ssy,
    ENGINES,
)
from apps.home.calculators.registry import (
    CALCULATORS,
    DEFAULT_CATEGORIES,
    PHASE1_SLUGS,
    SLUG_REDIRECTS,
    engine_slug_for,
    get_spec,
)
from apps.home.views.calculators import build_hub_tabs


class SipEngineTests(SimpleTestCase):
    def test_sip_24_months_12_percent(self):
        result = sip(monthly_amount=5000, years=2, annual_rate=12)
        self.assertAlmostEqual(result['future_value'], 136216, delta=1)
        self.assertEqual(result['invested'], 120000)

    def test_goal_sip_inverts_sip(self):
        forward = sip(monthly_amount=10000, years=10, annual_rate=12)
        reverse = goal_sip(target_amount=forward['future_value'], years=10, annual_rate=12)
        self.assertAlmostEqual(reverse['monthly_sip'], 10000, delta=2)

    def test_zero_rate_sip(self):
        result = sip(monthly_amount=1000, years=1, annual_rate=0)
        self.assertEqual(result['future_value'], 12000)
        self.assertEqual(result['gain'], 0)


class OtherEngineTests(SimpleTestCase):
    def test_lumpsum_monthly_compounding(self):
        result = lumpsum(amount=100000, years=1, annual_rate=12)
        expected = round(100000 * ((1 + 0.01) ** 12))
        self.assertEqual(result['future_value'], expected)

    def test_emi_known_value(self):
        result = emi(loan_amount=1000000, years=1, annual_rate=12)
        self.assertTrue(result['emi'] > 0)
        self.assertEqual(result['principal'], 1000000)
        self.assertGreater(result['total_payment'], result['principal'])

    def test_compound_interest_yearly(self):
        result = compound_interest(principal=10000, years=2, annual_rate=10, frequency=1)
        self.assertEqual(result['future_value'], 12100)

    def test_inflation(self):
        result = inflation(current_amount=100, years=1, inflation_rate=10)
        self.assertEqual(result['future_cost'], 110)

    def test_ppf_zero_rate(self):
        result = ppf(annual_amount=150000, years=15, annual_rate=0)
        self.assertEqual(result['future_value'], 2250000)

    def test_hlv_floors_at_zero(self):
        result = human_life_value(annual_income=500000, years_to_retire=10, existing_savings=10000000)
        self.assertEqual(result['cover_needed'], 0)

    def test_insurance_smoker_higher_than_nonsmoker(self):
        base = insurance_premium(calc_type='health', age=30, gender='male', coverage=500000, term=15, smoking='no')
        smoker = insurance_premium(calc_type='health', age=30, gender='male', coverage=500000, term=15, smoking='yes')
        self.assertGreater(smoker['yearly_premium'], base['yearly_premium'])

    def test_step_up_beats_flat_sip(self):
        flat = sip(monthly_amount=5000, years=5, annual_rate=12)
        stepped = step_up_sip(monthly_amount=5000, years=5, annual_rate=12, step_up_percent=10)
        self.assertGreater(stepped['future_value'], flat['future_value'])

    def test_dispatcher_sip(self):
        result = calculate('sip', {'monthly_amount': 5000, 'years': 2, 'annual_rate': 12})
        self.assertAlmostEqual(result['future_value'], 136216, delta=1)

    def test_dispatcher_seo_slug(self):
        result = calculate('sip-calculator', {'monthly_amount': 5000, 'years': 2, 'annual_rate': 12})
        self.assertAlmostEqual(result['future_value'], 136216, delta=1)

    def test_dispatcher_unknown_slug(self):
        with self.assertRaises(ValueError):
            calculate('not-a-calc', {})


class RegistryTests(SimpleTestCase):
    def test_phase1_specs_exist(self):
        for slug in PHASE1_SLUGS:
            spec = get_spec(slug)
            self.assertIsNotNone(spec, slug)
            self.assertTrue(spec['engine_ready'], slug)
            self.assertTrue(spec['fields'], slug)

    def test_legacy_slugs_resolve(self):
        for old, new in SLUG_REDIRECTS.items():
            spec = get_spec(old)
            self.assertIsNotNone(spec, old)
            self.assertEqual(spec['slug'], new)

    def test_catalog_slugs_unique(self):
        slugs = [item['slug'] for item in CALCULATORS]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_category_slugs_unique(self):
        slugs = [item['slug'] for item in DEFAULT_CATEGORIES]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_every_catalog_engine_is_ready_and_runs(self):
        for item in CALCULATORS:
            spec = get_spec(item['slug'])
            self.assertTrue(spec['engine_ready'], item['slug'])
            engine = engine_slug_for(item['slug'])
            self.assertIn(engine, ENGINES, item['slug'])
            inputs = {field['id']: field['default'] if field.get('default') != '' else '2026-01-15'
                      for field in spec['fields']}
            result = calculate(item['slug'], inputs)
            self.assertIn('primary', result, item['slug'])


class ExtraEngineTests(SimpleTestCase):
    def test_gratuity_cap(self):
        result = gratuity(monthly_salary=200000, years=30)
        self.assertEqual(result['gratuity'], 2000000)

    def test_gst_exclusive(self):
        result = gst(amount=1000, gst_rate=18, mode='exclusive')
        self.assertEqual(result['gst_amount'], 180)
        self.assertEqual(result['total'], 1180)

    def test_income_tax_rebate_at_12_lakh(self):
        result = income_tax(annual_income=1200000)
        self.assertEqual(result['total_tax'], 0)

    def test_bond_yield(self):
        result = bond_yield(face_value=1000, price=1000, coupon=7)
        self.assertAlmostEqual(result['current_yield'], 7.0, delta=0.01)

    def test_bmi_normal(self):
        result = bmi_calculator(weight_kg=70, height_cm=175)
        self.assertEqual(result['category'], 'Normal')

    def test_idv_year_one(self):
        result = idv_calculator(ex_showroom=1000000, vehicle_age=1)
        self.assertEqual(result['idv'], 850000)

    def test_section_80d_caps(self):
        result = section_80d(self_premium=40000, parents_premium=40000, self_senior='no', parents_senior='yes', preventive=5000)
        self.assertEqual(result['self_deduction'], 25000)
        self.assertEqual(result['parents_deduction'], 40000)

    def test_ssy_caps_contribution(self):
        result = ssy(annual_amount=200000, years=21, annual_rate=0)
        self.assertEqual(result['invested'], 150000 * 21)


class JsCatalogTests(SimpleTestCase):
    def test_js_file_registers_every_public_slug(self):
        from pathlib import Path
        js = Path('static/js/calculators/engines.js').read_text(encoding='utf-8')
        for item in CALCULATORS:
            engine = engine_slug_for(item['slug'])
            self.assertIn("'" + engine + "'", js, item['slug'])


class DetailLayoutTests(SimpleTestCase):
    def test_detail_template_has_no_category_tabs_or_inner_scroll_cta(self):
        from pathlib import Path
        html = Path('templates/public/calculators/detail.html').read_text(encoding='utf-8')
        css = Path('static/css/calculators.css').read_text(encoding='utf-8')
        self.assertNotIn('_tabs.html', html)
        self.assertNotIn('mobile-sticky-cta', html)
        self.assertNotIn('100dvh', css)
        self.assertIn('flex-wrap: wrap', css)


class HubTabTests(SimpleTestCase):
    def test_skips_empty_and_keeps_category_order(self):
        insurance = type('Cat', (), {'id': 1, 'slug': 'insurance'})()
        fitness = type('Cat', (), {'id': 2, 'slug': 'fitness'})()
        planning = type('Cat', (), {'id': 3, 'slug': 'planning'})()
        calc = type('Calc', (), {'category_id': 1})()
        tabs = build_hub_tabs([insurance, fitness, planning], [calc])
        self.assertEqual([tab['category'].slug for tab in tabs], ['insurance'])
        self.assertEqual(tabs[0]['count'], 1)
