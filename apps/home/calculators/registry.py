"""Catalog of financial and fitness calculators.

Formulas live in engines.py / static JS. This file is metadata + input schema only.
Admin cannot invent new slugs — they toggle and edit copy on seeded rows.
"""
from copy import deepcopy

DEFAULT_DISCLAIMER = (
    'Estimates only. Not investment or insurance advice. '
    'Actual premiums and returns vary. Consult a licensed PadosiAgent.'
)
FITNESS_DISCLAIMER = (
    'Educational estimates only. Not medical advice. '
    'Speak with a qualified health professional for personal guidance.'
)
DEFAULT_CTA_TEXT = 'Find a PadosiAgent'
DEFAULT_CTA_URL = '/find-agents/?openFilter=1'
BLUE = '#273c8e'
GREEN = '#10b981'
AMBER = '#f59e0b'
RED = '#ef4444'
SLATE = '#94a3b8'

DEFAULT_CATEGORIES = [
    {
        'slug': 'insurance', 'name': 'Insurance', 'icon_class': 'fa-solid fa-shield-heart',
        'sort_order': 10, 'is_active': True,
        'meta_title': 'Insurance Calculators India | Term, Health, Motor | PadosiAgent',
        'meta_description': 'Free term, health, motor, ULIP and life cover calculators. Educational estimates — talk to a licensed PadosiAgent.',
    },
    {
        'slug': 'investment', 'name': 'Investment', 'icon_class': 'fa-solid fa-chart-line',
        'sort_order': 20, 'is_active': True,
        'meta_title': 'Investment Calculators India | SIP, ULIP, NPS | PadosiAgent',
        'meta_description': 'SIP, lumpsum, ULIP, NPS and compounding calculators to plan investments in India.',
    },
    {
        'slug': 'loans', 'name': 'Loans', 'icon_class': 'fa-solid fa-building-columns',
        'sort_order': 30, 'is_active': True,
        'meta_title': 'EMI Calculators India | Home, Car, Personal Loan | PadosiAgent',
        'meta_description': 'Calculate home loan, car loan and personal loan EMI with interest and total payout.',
    },
    {
        'slug': 'retirement', 'name': 'Retirement', 'icon_class': 'fa-solid fa-umbrella-beach',
        'sort_order': 40, 'is_active': True,
        'meta_title': 'Retirement Calculators India | NPS, EPF, Pension | PadosiAgent',
        'meta_description': 'Plan retirement corpus, NPS, EPF, pension and annuity payouts online.',
    },
    {
        'slug': 'savings', 'name': 'Savings', 'icon_class': 'fa-solid fa-piggy-bank',
        'sort_order': 50, 'is_active': True,
        'meta_title': 'Savings Calculators India | FD, PPF, RD, SSY | PadosiAgent',
        'meta_description': 'Estimate FD, PPF, RD, SSY and savings account growth with compounding.',
    },
    {
        'slug': 'tax', 'name': 'Tax', 'icon_class': 'fa-solid fa-receipt',
        'sort_order': 60, 'is_active': True,
        'meta_title': 'Tax Calculators India | Income Tax, HRA, 80D, GST | PadosiAgent',
        'meta_description': 'Income tax, HRA, Section 80D and GST calculators for India.',
    },
    {
        'slug': 'planning', 'name': 'Planning', 'icon_class': 'fa-solid fa-bullseye',
        'sort_order': 70, 'is_active': True,
        'meta_title': 'Financial Planning Calculators | Inflation, Net Worth | PadosiAgent',
        'meta_description': 'Inflation, future value, net worth and asset allocation calculators.',
    },
    {
        'slug': 'fitness', 'name': 'Fitness', 'icon_class': 'fa-solid fa-heart-pulse',
        'sort_order': 80, 'is_active': True,
        'meta_title': 'Fitness Calculators | BMI, BMR, Pregnancy | PadosiAgent',
        'meta_description': 'BMI, calorie, BMR, body fat, ovulation and pregnancy calculators.',
    },
]
CATEGORIES = [(c['slug'], c['name']) for c in DEFAULT_CATEGORIES]
CATEGORY_LABELS = dict(CATEGORIES)

SLUG_REDIRECTS = {
    'sip': 'sip-calculator',
    'goal-sip': 'goal-sip-calculator',
    'step-up-sip': 'step-up-sip-calculator',
    'lumpsum': 'lumpsum-calculator',
    'emi': 'emi-calculator',
    'compound-interest': 'compound-interest-calculator',
    'inflation': 'inflation-calculator',
    'fd': 'fd-calculator',
    'ppf': 'ppf-calculator',
    'human-life-value': 'human-life-value-calculator',
    'insurance-premium': 'health-insurance-calculator',
    'swp': 'swp-calculator',
    'nps': 'nps-calculator',
    'retirement': 'retirement-calculator',
    'pension': 'pension-calculator',
    'epf': 'epf-calculator',
    'rd': 'rd-calculator',
    'gratuity': 'gratuity-calculator',
    'cost-of-delay': 'cost-of-delay-calculator',
    'power-of-compounding': 'power-of-compounding-calculator',
    'future-value': 'future-value-calculator',
    'increasing-contribution': 'increasing-contribution-calculator',
    'bond-yield': 'bond-yield-calculator',
    'annuity-payout': 'annuity-payout-calculator',
    'net-worth': 'net-worth-calculator',
    'asset-allocation': 'asset-allocation-calculator',
    'present-value': 'present-value-calculator',
    'income-tax': 'income-tax-calculator',
    'hra': 'hra-calculator',
    'gst': 'gst-calculator',
}

PHASE1_SLUGS = frozenset(SLUG_REDIRECTS.values())

_DONUT = {
    'chart': 'donut',
    'chart_slices': [
        {'key': 'invested', 'label': 'Invested', 'color': BLUE},
        {'key': 'gain', 'label': 'Est. returns', 'color': GREEN},
    ],
    'primary': {'key': 'future_value', 'label': 'Future value'},
    'rows': [
        {'key': 'invested', 'label': 'Amount invested'},
        {'key': 'gain', 'label': 'Estimated returns'},
    ],
    'period_toggle': False,
}

_PREMIUM = {
    'chart': 'none',
    'chart_slices': [],
    'primary': {'key': 'monthly_premium', 'label': 'Estimated premium'},
    'rows': [
        {'key': 'monthly_premium', 'label': 'Monthly'},
        {'key': 'yearly_premium', 'label': 'Yearly'},
        {'key': 'coverage', 'label': 'Coverage'},
    ],
    'period_toggle': True,
    'period_keys': {'monthly': 'monthly_premium', 'yearly': 'yearly_premium'},
}


def _inr(field_id, label, default, min_v, max_v, step=500):
    return {
        'id': field_id, 'label': label, 'type': 'range',
        'min': min_v, 'max': max_v, 'step': step, 'default': default,
        'prefix': '₹', 'format': 'inr',
    }


def _pct(field_id, label, default, min_v=1, max_v=30, step=0.5):
    return {
        'id': field_id, 'label': label, 'type': 'range',
        'min': min_v, 'max': max_v, 'step': step, 'default': default,
        'suffix': '%', 'format': 'percent',
    }


def _yrs(field_id, label, default, min_v=1, max_v=40, step=1):
    return {
        'id': field_id, 'label': label, 'type': 'range',
        'min': min_v, 'max': max_v, 'step': step, 'default': default,
        'suffix': ' years', 'format': 'years',
    }


def _num(field_id, label, default, min_v, max_v, step=1, suffix='', fmt='number'):
    return {
        'id': field_id, 'label': label, 'type': 'range',
        'min': min_v, 'max': max_v, 'step': step, 'default': default,
        'suffix': suffix, 'format': fmt,
    }


def _date(field_id, label, default=''):
    return {'id': field_id, 'label': label, 'type': 'date', 'default': default}


def _radio(field_id, label, default, options):
    return {'id': field_id, 'label': label, 'type': 'radio', 'default': default, 'options': options}


def _select(field_id, label, default, options):
    return {'id': field_id, 'label': label, 'type': 'select', 'default': default, 'options': options}


def _faq(*pairs):
    return [{'q': q, 'a': a} for q, a in pairs]


def _spec(slug, title, short, category, icon, fields, outputs, faqs, sort_order,
          engine_ready=True, meta_title=None, meta_description=None, engine=None,
          disclaimer=None):
    return {
        'slug': slug,
        'title': title,
        'short_description': short,
        'category': category,
        'icon_class': icon,
        'engine_ready': engine_ready,
        'sort_order': sort_order,
        'engine': engine or slug,
        'meta_title': meta_title or f'{title} India | Calculate Online | PadosiAgent',
        'meta_description': meta_description or short,
        'disclaimer': disclaimer or DEFAULT_DISCLAIMER,
        'cta_text': DEFAULT_CTA_TEXT,
        'cta_url': DEFAULT_CTA_URL,
        'fields': fields,
        'outputs': outputs,
        'faqs': faqs,
    }


_GENDER = _radio('gender', 'Gender', 'male', [
    {'value': 'male', 'label': 'Male'},
    {'value': 'female', 'label': 'Female'},
])
_SMOKING = _radio('smoking', 'Lifestyle', 'no', [
    {'value': 'no', 'label': 'Non-smoker'},
    {'value': 'yes', 'label': 'Smoker'},
])

_PREMIUM_FAQ = _faq(
    ('Is this the premium I will pay?',
     'No. This is a simplified educational estimate. Insurers price on medicals, occupation, city, riders and underwriting. Get a real quote via a PadosiAgent.'),
    ('Are returns or premiums guaranteed?',
     'No. Use this to size a conversation, then compare licensed quotes.'),
    ('Who can help me buy the right cover?',
     'A licensed PadosiAgent can match cover, riders and budget to your family.'),
)

_SIP_FAQ = _faq(
    ('How is SIP maturity calculated?',
     'The calculator uses the standard annuity-due formula: FV = P × [((1 + r)^n − 1) / r] × (1 + r), where r is the monthly rate and n is the number of instalments.'),
    ('Are these returns guaranteed?',
     'No. The rate you enter is an assumption. Mutual fund returns vary with markets. This is an educational estimate, not a forecast.'),
    ('What SIP amount should I start with?',
     'Start with an amount you can continue every month. A licensed PadosiAgent can help match the SIP to your goals, risk profile and existing insurance cover.'),
    ('SIP or lumpsum?',
     'Lumpsum invests everything at once. SIP spreads purchases over time. Use both calculators to compare.'),
)

CALCULATORS = [
    _spec(
        'term-insurance-calculator', 'Term Insurance Calculator',
        'Estimate term life premium from age, cover, term and lifestyle.',
        'insurance', 'fa-solid fa-file-shield',
        [_yrs('age', 'Your age', 30, 18, 65), _GENDER,
         _inr('coverage', 'Life cover', 10000000, 1000000, 50000000, 100000),
         _yrs('term', 'Policy term', 30, 5, 40), _SMOKING],
        _PREMIUM, _PREMIUM_FAQ, 5,
        meta_description='Free term insurance calculator India. Estimate premium for life cover by age, term and smoking status.',
    ),
    _spec(
        'life-insurance-calculator', 'Life Insurance Calculator',
        'Educational life cover premium estimate for endowment-style plans.',
        'insurance', 'fa-solid fa-heart',
        [_yrs('age', 'Your age', 30, 18, 65), _GENDER,
         _inr('coverage', 'Sum assured', 5000000, 500000, 25000000, 100000),
         _yrs('term', 'Policy term', 20, 5, 40), _SMOKING],
        _PREMIUM, _PREMIUM_FAQ, 8,
        meta_description='Calculate life insurance premium online. Educational estimate for life cover in India.',
    ),
    _spec(
        'health-insurance-calculator', 'Health Insurance Calculator',
        'Estimate health insurance premium for you or your family.',
        'insurance', 'fa-solid fa-suitcase-medical',
        [_yrs('age', 'Oldest insured age', 30, 18, 75), _GENDER,
         _inr('coverage', 'Sum insured', 500000, 200000, 10000000, 50000),
         _num('members', 'Family members', 1, 1, 8, 1, '', 'number'),
         _yrs('term', 'Policy term', 1, 1, 3), _SMOKING],
        _PREMIUM, _PREMIUM_FAQ, 10,
        meta_description='Health insurance premium calculator India. Estimate mediclaim cost by age, cover and family size.',
    ),
    _spec(
        'human-life-value-calculator', 'Human Life Value Calculator',
        'Estimate life cover as income × years to retire, minus savings.',
        'insurance', 'fa-solid fa-heart-pulse',
        [_inr('annual_income', 'Annual income', 1200000, 100000, 20000000, 50000),
         _yrs('years_to_retire', 'Years to retirement', 25, 5, 40),
         _inr('existing_savings', 'Existing savings / cover', 0, 0, 50000000, 50000)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'cover_needed', 'label': 'Cover needed', 'color': BLUE},
                {'key': 'existing_savings', 'label': 'Already covered', 'color': SLATE},
            ],
            'primary': {'key': 'cover_needed', 'label': 'Suggested life cover'},
            'rows': [
                {'key': 'income_stream', 'label': 'Income to replace'},
                {'key': 'existing_savings', 'label': 'Existing savings / cover'},
            ],
            'period_toggle': False,
        },
        _faq(
            ('Is this the cover I should buy?',
             'It is a simple educational starting point. Liabilities, dependents, inflation and existing policies change the number. A licensed agent should size the actual term plan.'),
            ('How is HLV calculated here?',
             'Annual income × years to retirement, minus existing savings and cover.'),
        ),
        12,
        meta_description='Human life value calculator India. Estimate how much term cover your family may need.',
    ),
    _spec(
        'life-cover-calculator', 'Life Cover Calculator',
        'Income replacement plus liabilities, minus existing life cover.',
        'insurance', 'fa-solid fa-user-shield',
        [_inr('annual_income', 'Annual income', 1200000, 100000, 20000000, 50000),
         _yrs('years_to_retire', 'Years of income to replace', 25, 5, 40),
         _inr('liabilities', 'Loans / liabilities', 0, 0, 50000000, 50000),
         _inr('existing_cover', 'Existing life cover', 0, 0, 50000000, 50000)],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'cover_needed', 'label': 'Cover needed'},
            'rows': [
                {'key': 'income_stream', 'label': 'Income to replace'},
                {'key': 'liabilities', 'label': 'Liabilities'},
                {'key': 'existing_cover', 'label': 'Existing cover'},
            ],
            'period_toggle': False,
        },
        _faq(
            ('How is life cover sized?',
             'Income × years to replace, plus loans, minus cover you already have. Talk to an agent before you buy.'),
        ),
        14,
    ),
    _spec(
        'home-loan-insurance-calculator', 'Home Loan Insurance Calculator',
        'Estimate cover near your outstanding home loan and a decreasing-term premium.',
        'insurance', 'fa-solid fa-house-chimney-crack',
        [_inr('loan_amount', 'Outstanding loan', 4000000, 100000, 50000000, 50000),
         _yrs('years', 'Remaining tenure', 15, 1, 30),
         _pct('annual_rate', 'Loan rate (p.a.)', 8.5, 6, 15, 0.1)],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'cover_needed', 'label': 'Suggested cover'},
            'rows': [
                {'key': 'outstanding', 'label': 'Outstanding loan'},
                {'key': 'yearly_premium', 'label': 'Est. yearly premium'},
            ],
            'period_toggle': False,
        },
        _PREMIUM_FAQ, 16,
        meta_description='Home loan insurance calculator. Estimate cover equal to outstanding housing loan.',
    ),
    _spec(
        'lic-calculator', 'LIC Calculator',
        'Educational LIC-style premium and maturity estimate.',
        'insurance', 'fa-solid fa-landmark',
        [_yrs('age', 'Your age', 30, 18, 60),
         _inr('coverage', 'Sum assured', 1000000, 100000, 10000000, 50000),
         _yrs('term', 'Policy term', 20, 10, 35)],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'yearly_premium', 'label': 'Est. yearly premium'},
            'rows': [
                {'key': 'monthly_premium', 'label': 'Monthly'},
                {'key': 'bonus', 'label': 'Est. bonus'},
                {'key': 'maturity', 'label': 'Est. maturity'},
            ],
            'period_toggle': False,
        },
        _faq(
            ('Is this an official LIC quote?',
             'No. Bonus rates and plan rules differ. Use this to prepare, then get a licensed quote.'),
            ('LIC vs term + SIP?',
             'Term cover is usually cheaper per rupee of protection. Compare with the ULIP vs mutual fund calculator.'),
        ),
        18,
        meta_description='LIC calculator India. Estimate premium and maturity for an educational endowment-style plan.',
    ),
    _spec(
        'ulip-calculator', 'ULIP Calculator',
        'Project ULIP corpus after estimated fund-management charges.',
        'insurance', 'fa-solid fa-chart-pie',
        [_inr('monthly_amount', 'Monthly premium', 5000, 1000, 100000, 500),
         _yrs('years', 'Premium paying term', 15, 5, 30),
         _pct('annual_rate', 'Gross return (p.a.)', 10, 4, 15),
         _pct('charge_percent', 'Charges (p.a.)', 2.25, 0.5, 5, 0.05)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'invested', 'label': 'Premiums paid', 'color': BLUE},
                {'key': 'gain', 'label': 'Est. returns', 'color': GREEN},
            ],
            'primary': {'key': 'future_value', 'label': 'Est. fund value'},
            'rows': [
                {'key': 'invested', 'label': 'Premiums paid'},
                {'key': 'charge_drag', 'label': 'Charge impact'},
            ],
            'period_toggle': False,
        },
        _faq(
            ('Are ULIP returns guaranteed?',
             'No. Fund value depends on markets and charges. Investment risk in ULIPs is borne by the policyholder.'),
            ('ULIP or term + mutual fund?',
             'Many advisors compare a cheap term plan plus SIP with a ULIP. Use the ULIP vs mutual fund calculator.'),
        ),
        20,
        meta_description='ULIP calculator India. Estimate maturity value after charges on a unit-linked insurance plan.',
    ),
    _spec(
        'car-insurance-calculator', 'Car Insurance Calculator',
        'Educational own-damage plus third-party premium from IDV, age and NCB.',
        'insurance', 'fa-solid fa-car',
        [_inr('idv', 'IDV', 600000, 50000, 5000000, 10000),
         _num('vehicle_age', 'Vehicle age', 3, 0, 15, 1, ' years', 'years'),
         _pct('ncb_percent', 'NCB', 20, 0, 50, 5)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'od_premium', 'label': 'Own damage', 'color': BLUE},
                {'key': 'tp_premium', 'label': 'Third party', 'color': AMBER},
            ],
            'primary': {'key': 'yearly_premium', 'label': 'Est. yearly premium'},
            'rows': [
                {'key': 'od_premium', 'label': 'Own damage'},
                {'key': 'tp_premium', 'label': 'Third party'},
                {'key': 'idv', 'label': 'IDV'},
            ],
            'period_toggle': False,
        },
        _PREMIUM_FAQ, 22,
        meta_description='Car insurance calculator India. Estimate OD and third-party premium from IDV and NCB.',
    ),
    _spec(
        'bike-insurance-calculator', 'Bike Insurance Calculator',
        'Educational two-wheeler OD plus third-party premium estimate.',
        'insurance', 'fa-solid fa-motorcycle',
        [_inr('idv', 'IDV', 80000, 10000, 500000, 1000),
         _num('vehicle_age', 'Vehicle age', 3, 0, 15, 1, ' years', 'years'),
         _pct('ncb_percent', 'NCB', 20, 0, 50, 5)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'od_premium', 'label': 'Own damage', 'color': BLUE},
                {'key': 'tp_premium', 'label': 'Third party', 'color': AMBER},
            ],
            'primary': {'key': 'yearly_premium', 'label': 'Est. yearly premium'},
            'rows': [
                {'key': 'od_premium', 'label': 'Own damage'},
                {'key': 'tp_premium', 'label': 'Third party'},
            ],
            'period_toggle': False,
        },
        _PREMIUM_FAQ, 24,
        meta_description='Bike insurance calculator India. Estimate two-wheeler premium from IDV, age and NCB.',
    ),
    _spec(
        'idv-calculator', 'IDV Calculator',
        'Insured declared value from ex-showroom price and vehicle age.',
        'insurance', 'fa-solid fa-tag',
        [_inr('ex_showroom', 'Ex-showroom price', 800000, 30000, 8000000, 10000),
         _num('vehicle_age', 'Vehicle age', 3, 0, 15, 0.5, ' years', 'years')],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'idv', 'label': 'Estimated IDV'},
            'rows': [
                {'key': 'ex_showroom', 'label': 'Ex-showroom'},
                {'key': 'depreciation', 'label': 'Depreciation'},
            ],
            'period_toggle': False,
        },
        _faq(
            ('What is IDV?',
             'Insured declared value is the maximum own-damage payout. Insurers apply a depreciation schedule to ex-showroom price.'),
            ('Is this the exact insurer IDV?',
             'It follows a typical IRDAI-style schedule. Insurers may differ. Confirm on the policy.'),
        ),
        26,
        meta_description='IDV calculator India. Estimate car or bike insured declared value from ex-showroom price and age.',
    ),
    _spec(
        'travel-insurance-calculator', 'Travel Insurance Calculator',
        'Estimate trip premium from days, travellers, cover and destination.',
        'insurance', 'fa-solid fa-plane',
        [_num('trip_days', 'Trip days', 7, 1, 180, 1, ' days', 'number'),
         _num('travellers', 'Travellers', 1, 1, 10, 1, '', 'number'),
         _inr('coverage', 'Medical cover', 500000, 100000, 10000000, 50000),
         _select('destination_type', 'Destination', 'asia', [
             {'value': 'domestic', 'label': 'India'},
             {'value': 'asia', 'label': 'Asia'},
             {'value': 'worldwide', 'label': 'Worldwide'},
         ])],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'yearly_premium', 'label': 'Est. trip premium'},
            'rows': [
                {'key': 'per_person', 'label': 'Per person'},
                {'key': 'coverage', 'label': 'Medical cover'},
            ],
            'period_toggle': False,
        },
        _PREMIUM_FAQ, 28,
        meta_description='Travel insurance calculator India. Estimate trip premium by days, destination and cover.',
    ),
    _spec(
        'section-80d-calculator', 'Section 80D Calculator',
        'Estimate health-insurance tax deduction for self and parents.',
        'tax', 'fa-solid fa-file-invoice',
        [_inr('self_premium', 'Self / family premium', 25000, 0, 100000, 1000),
         _inr('parents_premium', 'Parents premium', 25000, 0, 100000, 1000),
         _inr('preventive', 'Preventive health check', 0, 0, 5000, 500),
         _radio('self_senior', 'You are 60+', 'no', [{'value': 'no', 'label': 'No'}, {'value': 'yes', 'label': 'Yes'}]),
         _radio('parents_senior', 'Parents 60+', 'no', [{'value': 'no', 'label': 'No'}, {'value': 'yes', 'label': 'Yes'}])],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'total_deduction', 'label': '80D deduction'},
            'rows': [
                {'key': 'self_deduction', 'label': 'Self / family'},
                {'key': 'parents_deduction', 'label': 'Parents'},
            ],
            'period_toggle': False,
        },
        _faq(
            ('What is the 80D limit?',
             'Typically ₹25,000 (₹50,000 if senior) for self/family and a separate limit for parents. Preventive checks up to ₹5,000 sit inside the cap. Tax laws change — confirm with an advisor.'),
        ),
        30,
        meta_description='Section 80D calculator. Estimate income-tax deduction on health insurance premiums in India.',
    ),
    _spec(
        'ulip-vs-mutual-fund-calculator', 'ULIP vs Mutual Fund Calculator',
        'Compare a ULIP with term cover plus a mutual fund SIP.',
        'insurance', 'fa-solid fa-scale-balanced',
        [_inr('monthly_amount', 'Monthly amount', 10000, 1000, 100000, 500),
         _yrs('years', 'Period', 20, 5, 30),
         _pct('ulip_rate', 'ULIP gross return', 10, 4, 15),
         _pct('mf_rate', 'Mutual fund return', 12, 4, 18),
         _pct('charge_percent', 'ULIP charges', 2.25, 0.5, 5, 0.05),
         _inr('term_premium', 'Term premium / month', 800, 200, 10000, 50)],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'term_plus_sip', 'label': 'Term + SIP value'},
            'rows': [
                {'key': 'ulip_value', 'label': 'ULIP fund value'},
                {'key': 'mf_value', 'label': 'MF corpus'},
                {'key': 'difference', 'label': 'Difference'},
            ],
            'period_toggle': False,
        },
        _faq(
            ('Why compare term + SIP with ULIP?',
             'A term plan covers life; a SIP invests the rest. ULIPs bundle both with charges. This is educational, not a recommendation.'),
        ),
        32,
    ),
    _spec(
        'endowment-vs-mutual-fund-calculator', 'Endowment vs Mutual Fund Calculator',
        'Compare a traditional endowment with term cover plus SIP.',
        'insurance', 'fa-solid fa-arrows-left-right',
        [_inr('monthly_amount', 'Monthly amount', 10000, 1000, 100000, 500),
         _yrs('years', 'Period', 20, 10, 30),
         _pct('endowment_rate', 'Endowment return', 5, 3, 8),
         _pct('mf_rate', 'Mutual fund return', 12, 4, 18),
         _inr('term_premium', 'Term premium / month', 800, 200, 10000, 50)],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'term_plus_sip', 'label': 'Term + SIP value'},
            'rows': [
                {'key': 'endowment_value', 'label': 'Endowment value'},
                {'key': 'mf_value', 'label': 'MF corpus'},
                {'key': 'difference', 'label': 'Difference'},
            ],
            'period_toggle': False,
        },
        _faq(
            ('Are endowment returns guaranteed?',
             'Bonuses are not guaranteed. This uses the rate you enter as a planning assumption.'),
        ),
        34,
    ),
    _spec(
        'family-floater-vs-individual-calculator', 'Family Floater vs Individual Calculator',
        'Compare one family floater with separate individual health policies.',
        'insurance', 'fa-solid fa-people-group',
        [_num('members', 'Family members', 4, 2, 8, 1, '', 'number'),
         _yrs('age', 'Oldest member age', 35, 18, 75),
         _inr('coverage', 'Sum insured each', 500000, 200000, 5000000, 50000)],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'floater_premium', 'label': 'Floater yearly'},
            'rows': [
                {'key': 'individual_premium', 'label': 'All individual policies'},
                {'key': 'savings', 'label': 'Floater saves'},
            ],
            'period_toggle': False,
        },
        _faq(
            ('Floater or individual?',
             'Floaters often cost less but share one sum insured. Individual policies keep separate limits. An agent can match this to claims history and age.'),
        ),
        36,
    ),
    _spec(
        'super-top-up-calculator', 'Super Top-Up Calculator',
        'Estimate premium for extra health cover above a deductible.',
        'insurance', 'fa-solid fa-layer-group',
        [_inr('base_cover', 'Base policy cover', 500000, 200000, 5000000, 50000),
         _inr('deductible', 'Deductible / threshold', 500000, 200000, 5000000, 50000),
         _inr('extra_cover', 'Super top-up cover', 1500000, 500000, 10000000, 50000),
         _yrs('age', 'Oldest insured age', 35, 18, 75)],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'yearly_premium', 'label': 'Est. yearly premium'},
            'rows': [
                {'key': 'total_cover', 'label': 'Total cover'},
                {'key': 'deductible', 'label': 'Deductible'},
            ],
            'period_toggle': False,
        },
        _PREMIUM_FAQ, 38,
        meta_description='Super top-up health insurance calculator. Estimate premium for cover above your deductible.',
    ),
    _spec(
        'critical-illness-cover-calculator', 'Critical Illness Cover Calculator',
        'Educational critical-illness lump-sum premium estimate.',
        'insurance', 'fa-solid fa-notes-medical',
        [_yrs('age', 'Your age', 35, 18, 65),
         _inr('coverage', 'Lump-sum cover', 1000000, 200000, 10000000, 50000)],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'yearly_premium', 'label': 'Est. yearly premium'},
            'rows': [
                {'key': 'monthly_premium', 'label': 'Monthly'},
                {'key': 'coverage', 'label': 'Cover'},
            ],
            'period_toggle': False,
        },
        _PREMIUM_FAQ, 40,
    ),
    _spec(
        'sip-calculator', 'SIP Calculator',
        'Estimate the future value of a monthly systematic investment plan.',
        'investment', 'fa-solid fa-chart-line',
        [_inr('monthly_amount', 'Monthly SIP', 5000, 500, 200000, 500),
         _yrs('years', 'Investment period', 10, 1, 40),
         _pct('annual_rate', 'Expected return (p.a.)', 12, 1, 30)],
        _DONUT, _SIP_FAQ, 100,
        meta_title='SIP Calculator India | Calculate SIP Returns Online | PadosiAgent',
        meta_description='Calculate SIP returns with monthly investment, tenure and expected rate. Free online SIP calculator.',
    ),
    _spec(
        'goal-sip-calculator', 'Goal SIP Calculator',
        'Find the monthly SIP needed to reach a target corpus.',
        'investment', 'fa-solid fa-bullseye',
        [_inr('target_amount', 'Target amount', 10000000, 100000, 100000000, 50000),
         _yrs('years', 'Years to goal', 15, 1, 40),
         _pct('annual_rate', 'Expected return (p.a.)', 12, 1, 30)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'invested', 'label': 'You invest', 'color': BLUE},
                {'key': 'gain', 'label': 'Est. returns', 'color': GREEN},
            ],
            'primary': {'key': 'monthly_sip', 'label': 'Required monthly SIP'},
            'rows': [
                {'key': 'target_amount', 'label': 'Target corpus'},
                {'key': 'invested', 'label': 'Total you invest'},
                {'key': 'gain', 'label': 'Estimated returns'},
            ],
            'period_toggle': False,
        },
        _faq(
            ('How does a goal SIP calculator work?',
             'It reverses the SIP formula to find the monthly amount that, at your assumed return, grows to the target over the chosen years.'),
            ('Should I include inflation?',
             'For long goals, raise the target for inflation or use the Inflation calculator, then feed that future cost in here.'),
        ),
        105,
    ),
    _spec(
        'step-up-sip-calculator', 'Step-up SIP Calculator',
        'See how increasing your SIP every year grows the corpus faster.',
        'investment', 'fa-solid fa-arrow-trend-up',
        [_inr('monthly_amount', 'Starting monthly SIP', 5000, 500, 200000, 500),
         _yrs('years', 'Investment period', 15, 1, 40),
         _pct('annual_rate', 'Expected return (p.a.)', 12, 1, 30),
         _pct('step_up_percent', 'Yearly step-up', 10, 0, 50, 1)],
        _DONUT,
        _faq(('What is a step-up SIP?',
              'You raise the monthly instalment by a fixed percent each year, typically as income grows.')),
        110,
    ),
    _spec(
        'lumpsum-calculator', 'Lumpsum Calculator',
        'Project returns on a one-time mutual fund or investment amount.',
        'investment', 'fa-solid fa-sack-dollar',
        [_inr('amount', 'Investment amount', 100000, 1000, 10000000, 1000),
         _yrs('years', 'Investment period', 10, 1, 40),
         _pct('annual_rate', 'Expected return (p.a.)', 12, 1, 30)],
        _DONUT, _SIP_FAQ, 115,
    ),
    _spec(
        'investment-calculator', 'Investment Calculator',
        'Generic ROI projection for a one-time investment.',
        'investment', 'fa-solid fa-indian-rupee-sign',
        [_inr('amount', 'Investment amount', 100000, 1000, 10000000, 1000),
         _yrs('years', 'Investment period', 10, 1, 40),
         _pct('annual_rate', 'Expected return (p.a.)', 10, 1, 30)],
        _DONUT, _SIP_FAQ, 118, engine='lumpsum-calculator',
        meta_description='Investment calculator India. Project the future value of a lumpsum at an assumed rate of return.',
    ),
    _spec(
        'sip-vs-lumpsum-calculator', 'SIP vs Lumpsum Calculator',
        'Compare monthly SIP with investing the same total as a lumpsum.',
        'investment', 'fa-solid fa-code-compare',
        [_inr('monthly_amount', 'Monthly SIP', 5000, 500, 200000, 500),
         _yrs('years', 'Period', 10, 1, 40),
         _pct('annual_rate', 'Expected return (p.a.)', 12, 1, 30)],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'sip_value', 'label': 'SIP future value'},
            'rows': [
                {'key': 'lumpsum_value', 'label': 'Lumpsum future value'},
                {'key': 'sip_invested', 'label': 'SIP invested'},
                {'key': 'lumpsum_invested', 'label': 'Lumpsum invested'},
            ],
            'period_toggle': False,
        },
        _faq(
            ('Why is lumpsum often higher here?',
             'This comparison invests the full SIP total on day one. In real life you may not have that cash ready, and markets may not cooperate.'),
        ),
        120,
    ),
    _spec(
        'swp-calculator', 'SWP Calculator',
        'Plan systematic withdrawals from a lumpsum corpus.',
        'investment', 'fa-solid fa-money-bill-transfer',
        [_inr('amount', 'Corpus', 5000000, 100000, 50000000, 50000),
         _inr('monthly_withdrawal', 'Monthly withdrawal', 25000, 1000, 500000, 1000),
         _yrs('years', 'Period', 15, 1, 40),
         _pct('annual_rate', 'Expected return (p.a.)', 8, 1, 20)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'total_withdrawn', 'label': 'Withdrawn', 'color': GREEN},
                {'key': 'remaining', 'label': 'Remaining', 'color': BLUE},
            ],
            'primary': {'key': 'remaining', 'label': 'Corpus remaining'},
            'rows': [
                {'key': 'invested', 'label': 'Starting corpus'},
                {'key': 'total_withdrawn', 'label': 'Total withdrawn'},
            ],
            'period_toggle': False,
        }, [], 125,
    ),
    _spec(
        'compound-interest-calculator', 'Compound Interest Calculator',
        'See how compounding frequency changes the growth of money.',
        'investment', 'fa-solid fa-layer-group',
        [_inr('principal', 'Principal', 100000, 1000, 10000000, 1000),
         _yrs('years', 'Period', 10, 1, 40),
         _pct('annual_rate', 'Interest rate (p.a.)', 8, 1, 20),
         _select('frequency', 'Compounded', 4, [
             {'value': 1, 'label': 'Yearly'},
             {'value': 2, 'label': 'Half-yearly'},
             {'value': 4, 'label': 'Quarterly'},
             {'value': 12, 'label': 'Monthly'},
         ])],
        _DONUT,
        _faq(('Why does compounding frequency matter?',
              'Interest added more often earns interest sooner. Quarterly compounding is common on Indian FDs.')),
        130,
    ),
    _spec(
        'elss-calculator', 'ELSS Calculator',
        'Project tax-saving ELSS SIP returns (3-year lock-in).',
        'investment', 'fa-solid fa-file-invoice-dollar',
        [_inr('monthly_amount', 'Monthly SIP', 5000, 500, 12500, 500),
         _yrs('years', 'Investment period', 10, 3, 30),
         _pct('annual_rate', 'Expected return (p.a.)', 12, 6, 18)],
        _DONUT,
        _faq(
            ('What is the ELSS lock-in?',
             'Equity-linked saving schemes have a 3-year lock-in. Tax benefits depend on the regime you choose.'),
        ),
        135, engine='sip-calculator',
        meta_description='ELSS calculator India. Estimate tax-saving mutual fund SIP returns with a 3-year lock-in.',
    ),
    _spec(
        'bond-yield-calculator', 'Bond Yield Calculator',
        'Estimate current yield on a bond from price and coupon.',
        'investment', 'fa-solid fa-file-invoice-dollar',
        [_inr('face_value', 'Face value', 1000, 100, 100000, 100),
         _inr('price', 'Market price', 980, 100, 100000, 1),
         _pct('coupon', 'Coupon rate', 7, 1, 15)],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'current_yield', 'label': 'Current yield', 'format': 'percent'},
            'rows': [
                {'key': 'coupon_income', 'label': 'Yearly coupon'},
                {'key': 'price', 'label': 'Market price'},
            ],
            'period_toggle': False,
        }, [], 140,
    ),
    _spec(
        'emi-calculator', 'EMI Calculator',
        'Calculate monthly EMI, total interest and overall payout on a loan.',
        'loans', 'fa-solid fa-building-columns',
        [_inr('loan_amount', 'Loan amount', 2500000, 50000, 50000000, 10000),
         _yrs('years', 'Tenure', 20, 1, 30),
         _pct('annual_rate', 'Interest rate (p.a.)', 8.5, 1, 24, 0.1)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'principal', 'label': 'Principal', 'color': BLUE},
                {'key': 'total_interest', 'label': 'Interest', 'color': AMBER},
            ],
            'primary': {'key': 'emi', 'label': 'Monthly EMI'},
            'rows': [
                {'key': 'principal', 'label': 'Principal'},
                {'key': 'total_interest', 'label': 'Total interest'},
                {'key': 'total_payment', 'label': 'Total payment'},
            ],
            'period_toggle': False,
        },
        _faq(
            ('How is EMI calculated?',
             'EMI = P × r × (1 + r)^n / ((1 + r)^n − 1), where r is the monthly interest rate and n is the number of months.'),
            ('Does this include processing fees?',
             'No. Fees, insurance and prepayment charges are extra. Ask a PadosiAgent before you sign.'),
        ),
        200,
        meta_description='EMI calculator India. Calculate monthly EMI, interest and total payout for any loan.',
    ),
    _spec(
        'home-loan-emi-calculator', 'Home Loan EMI Calculator',
        'Housing-loan EMI with typical home-loan tenure and rate defaults.',
        'loans', 'fa-solid fa-house',
        [_inr('loan_amount', 'Home loan amount', 5000000, 500000, 50000000, 50000),
         _yrs('years', 'Tenure', 20, 5, 30),
         _pct('annual_rate', 'Interest rate (p.a.)', 8.5, 6, 15, 0.05)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'principal', 'label': 'Principal', 'color': BLUE},
                {'key': 'total_interest', 'label': 'Interest', 'color': AMBER},
            ],
            'primary': {'key': 'emi', 'label': 'Monthly EMI'},
            'rows': [
                {'key': 'principal', 'label': 'Principal'},
                {'key': 'total_interest', 'label': 'Total interest'},
                {'key': 'total_payment', 'label': 'Total payment'},
            ],
            'period_toggle': False,
        },
        _faq(
            ('Should I add home-loan insurance?',
             'Many lenders offer cover on the outstanding loan. Use the Home Loan Insurance calculator, then talk to an agent.'),
        ),
        205, engine='emi-calculator',
        meta_description='Home loan EMI calculator India. Estimate monthly EMI, interest and total payout.',
    ),
    _spec(
        'car-loan-emi-calculator', 'Car Loan EMI Calculator',
        'Estimate monthly EMI on a car loan.',
        'loans', 'fa-solid fa-car-side',
        [_inr('loan_amount', 'Car loan amount', 800000, 100000, 5000000, 10000),
         _yrs('years', 'Tenure', 5, 1, 8),
         _pct('annual_rate', 'Interest rate (p.a.)', 10, 7, 18, 0.1)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'principal', 'label': 'Principal', 'color': BLUE},
                {'key': 'total_interest', 'label': 'Interest', 'color': AMBER},
            ],
            'primary': {'key': 'emi', 'label': 'Monthly EMI'},
            'rows': [
                {'key': 'principal', 'label': 'Principal'},
                {'key': 'total_interest', 'label': 'Total interest'},
                {'key': 'total_payment', 'label': 'Total payment'},
            ],
            'period_toggle': False,
        }, [], 210, engine='emi-calculator',
        meta_description='Car loan EMI calculator India. Calculate monthly instalment and total interest.',
    ),
    _spec(
        'personal-loan-emi-calculator', 'Personal Loan EMI Calculator',
        'Estimate monthly EMI on an unsecured personal loan.',
        'loans', 'fa-solid fa-wallet',
        [_inr('loan_amount', 'Loan amount', 300000, 20000, 4000000, 5000),
         _yrs('years', 'Tenure', 3, 1, 6),
         _pct('annual_rate', 'Interest rate (p.a.)', 14, 10, 28, 0.1)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'principal', 'label': 'Principal', 'color': BLUE},
                {'key': 'total_interest', 'label': 'Interest', 'color': AMBER},
            ],
            'primary': {'key': 'emi', 'label': 'Monthly EMI'},
            'rows': [
                {'key': 'principal', 'label': 'Principal'},
                {'key': 'total_interest', 'label': 'Total interest'},
                {'key': 'total_payment', 'label': 'Total payment'},
            ],
            'period_toggle': False,
        }, [], 215, engine='emi-calculator',
    ),
    _spec(
        'nps-calculator', 'NPS Calculator',
        'Estimate National Pension System corpus and annuity.',
        'retirement', 'fa-solid fa-landmark',
        [_inr('monthly_amount', 'Monthly contribution', 5000, 500, 200000, 500),
         _yrs('years', 'Years to retire', 25, 5, 40),
         _pct('annual_rate', 'Expected return (p.a.)', 10, 6, 14)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'lump_sum', 'label': 'Lump sum (60%)', 'color': BLUE},
                {'key': 'annuity_corpus', 'label': 'Annuity (40%)', 'color': GREEN},
            ],
            'primary': {'key': 'future_value', 'label': 'NPS corpus'},
            'rows': [
                {'key': 'invested', 'label': 'Amount invested'},
                {'key': 'lump_sum', 'label': 'Lump sum (60%)'},
                {'key': 'yearly_pension', 'label': 'Est. yearly pension'},
            ],
            'period_toggle': False,
        }, [], 300,
        meta_description='NPS calculator India. Estimate National Pension System corpus, lump sum and annuity.',
    ),
    _spec(
        'retirement-calculator', 'Retirement Calculator',
        'Work out the corpus needed for a comfortable retirement.',
        'retirement', 'fa-solid fa-umbrella-beach',
        [_inr('monthly_expense', 'Monthly expense today', 50000, 5000, 500000, 1000),
         _yrs('years_to_retire', 'Years to retirement', 25, 1, 40),
         _yrs('retirement_years', 'Years in retirement', 25, 10, 40),
         _pct('inflation_rate', 'Inflation (p.a.)', 6, 2, 12),
         _pct('annual_rate', 'Post-retire return (p.a.)', 7, 4, 12)],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'corpus_needed', 'label': 'Corpus needed'},
            'rows': [
                {'key': 'future_expense', 'label': 'Monthly expense at retirement'},
                {'key': 'monthly_sip', 'label': 'SIP to build this corpus'},
            ],
            'period_toggle': False,
        }, [], 305,
    ),
    _spec(
        'pension-calculator', 'Pension Calculator',
        'Estimate how much to save for a desired pension.',
        'retirement', 'fa-solid fa-hand-holding-dollar',
        [_inr('monthly_pension', 'Desired monthly pension', 40000, 5000, 500000, 1000),
         _yrs('years', 'Years to save', 25, 5, 40),
         _pct('annual_rate', 'Expected return (p.a.)', 8, 4, 14)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'invested', 'label': 'You invest', 'color': BLUE},
                {'key': 'gain', 'label': 'Est. returns', 'color': GREEN},
            ],
            'primary': {'key': 'monthly_sip', 'label': 'Required monthly SIP'},
            'rows': [
                {'key': 'corpus_needed', 'label': 'Corpus needed'},
                {'key': 'invested', 'label': 'Total you invest'},
            ],
            'period_toggle': False,
        }, [], 310,
    ),
    _spec(
        'epf-calculator', 'EPF Calculator',
        'Project Employee Provident Fund corpus at retirement.',
        'retirement', 'fa-solid fa-briefcase',
        [_inr('monthly_amount', 'Monthly EPF contribution', 5000, 500, 100000, 500),
         _yrs('years', 'Years of service', 25, 1, 40),
         _pct('annual_rate', 'Interest rate (p.a.)', 8.25, 6, 10, 0.05)],
        _DONUT, [], 315,
    ),
    _spec(
        'gratuity-calculator', 'Gratuity Calculator',
        'Estimate statutory gratuity on retirement or exit.',
        'retirement', 'fa-solid fa-gift',
        [_inr('monthly_salary', 'Last drawn monthly salary', 50000, 5000, 500000, 1000),
         _yrs('years', 'Years of service', 20, 5, 40)],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'gratuity', 'label': 'Estimated gratuity'},
            'rows': [
                {'key': 'uncapped', 'label': 'Formula amount'},
                {'key': 'statutory_cap', 'label': 'Statutory cap'},
            ],
            'period_toggle': False,
        }, [], 320,
    ),
    _spec(
        'annuity-payout-calculator', 'Annuity Payout Calculator',
        'Estimate regular payouts from a retirement corpus.',
        'retirement', 'fa-solid fa-coins',
        [_inr('amount', 'Corpus', 5000000, 100000, 50000000, 50000),
         _yrs('years', 'Payout years', 20, 5, 40),
         _pct('annual_rate', 'Annuity rate (p.a.)', 6, 4, 10)],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'monthly_payout', 'label': 'Monthly payout'},
            'rows': [
                {'key': 'yearly_payout', 'label': 'Yearly payout'},
                {'key': 'total_payout', 'label': 'Total payout'},
                {'key': 'invested', 'label': 'Corpus'},
            ],
            'period_toggle': False,
        }, [], 325,
    ),
    _spec(
        'fd-calculator', 'FD Calculator',
        'Estimate fixed deposit maturity with quarterly compounding by default.',
        'savings', 'fa-solid fa-piggy-bank',
        [_inr('amount', 'Deposit amount', 100000, 1000, 10000000, 1000),
         _yrs('years', 'Tenure', 5, 1, 10),
         _pct('annual_rate', 'Interest rate (p.a.)', 7, 3, 12, 0.1),
         _select('frequency', 'Compounded', 4, [
             {'value': 1, 'label': 'Yearly'},
             {'value': 4, 'label': 'Quarterly'},
             {'value': 12, 'label': 'Monthly'},
         ])],
        _DONUT,
        _faq(('How do banks compound FD interest?',
              'Most Indian banks compound quarterly. TDS and payout options can change what you actually receive.')),
        400,
    ),
    _spec(
        'ppf-calculator', 'PPF Calculator',
        'Project PPF maturity for yearly contributions at the notified rate.',
        'savings', 'fa-solid fa-vault',
        [_inr('annual_amount', 'Yearly contribution', 150000, 500, 150000, 500),
         _yrs('years', 'Tenure', 15, 15, 50),
         _pct('annual_rate', 'Interest rate (p.a.)', 7.1, 6, 9, 0.1)],
        _DONUT,
        _faq(
            ('What is the PPF lock-in?',
             'PPF has a 15-year lock-in, extendable in 5-year blocks. The interest rate is set by the government and can change.'),
            ('Is the 7.1% rate guaranteed?',
             'No. Enter the latest official notified rate for a closer estimate.'),
        ),
        405,
    ),
    _spec(
        'ssy-calculator', 'SSY Calculator',
        'Sukanya Samriddhi Yojana maturity for yearly deposits.',
        'savings', 'fa-solid fa-child-dress',
        [_inr('annual_amount', 'Yearly deposit', 150000, 250, 150000, 250),
         _yrs('years', 'Tenure', 21, 15, 21),
         _pct('annual_rate', 'Interest rate (p.a.)', 8.2, 7, 10, 0.1)],
        _DONUT,
        _faq(
            ('Who can invest in SSY?',
             'A guardian can open an account for a girl child. Contribution and age rules apply — check the latest government notification.'),
        ),
        410,
        meta_description='SSY calculator India. Estimate Sukanya Samriddhi Yojana maturity and interest.',
    ),
    _spec(
        'rd-calculator', 'RD Calculator',
        'Estimate recurring deposit maturity value.',
        'savings', 'fa-solid fa-calendar-check',
        [_inr('monthly_amount', 'Monthly deposit', 5000, 500, 200000, 500),
         _yrs('years', 'Tenure', 5, 1, 10),
         _pct('annual_rate', 'Interest rate (p.a.)', 7, 4, 10, 0.1)],
        _DONUT, [], 415,
    ),
    _spec(
        'savings-calculator', 'Savings Calculator',
        'Project savings-account growth with quarterly compounding.',
        'savings', 'fa-solid fa-building-columns',
        [_inr('amount', 'Starting balance', 100000, 1000, 10000000, 1000),
         _yrs('years', 'Period', 5, 1, 20),
         _pct('annual_rate', 'Interest rate (p.a.)', 3.5, 1, 8, 0.1)],
        _DONUT, [], 420,
        meta_description='Savings calculator India. Estimate how a savings balance grows with compounding interest.',
    ),
    _spec(
        'income-tax-calculator', 'Income Tax Calculator',
        'Educational estimate of income tax under the new regime (FY 2025-26 slabs).',
        'tax', 'fa-solid fa-receipt',
        [_inr('annual_income', 'Taxable income', 1200000, 250000, 20000000, 10000)],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'total_tax', 'label': 'Tax payable'},
            'rows': [
                {'key': 'tax_before_cess', 'label': 'Tax before cess'},
                {'key': 'cess', 'label': 'Health & education cess (4%)'},
                {'key': 'take_home', 'label': 'Income after tax'},
            ],
            'period_toggle': False,
        },
        _faq(
            ('Which regime is this?',
             'New regime slabs with a rebate illustration up to ₹12 lakh, plus 4% cess. Not a filed-return computation.'),
        ),
        500,
        meta_description='Income tax calculator India. Estimate new-regime tax for FY 2025-26 slabs.',
    ),
    _spec(
        'hra-calculator', 'HRA Calculator',
        'Estimate House Rent Allowance exemption.',
        'tax', 'fa-solid fa-house',
        [_inr('basic', 'Basic salary (annual)', 600000, 100000, 10000000, 10000),
         _inr('hra_received', 'HRA received', 240000, 0, 5000000, 5000),
         _inr('rent_paid', 'Rent paid', 240000, 0, 5000000, 5000),
         _radio('city_type', 'City type', 'metro', [
             {'value': 'metro', 'label': 'Metro (50%)'},
             {'value': 'non_metro', 'label': 'Non-metro (40%)'},
         ])],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'exemption', 'label': 'HRA exemption'},
            'rows': [
                {'key': 'taxable_hra', 'label': 'Taxable HRA'},
                {'key': 'hra_received', 'label': 'HRA received'},
            ],
            'period_toggle': False,
        }, [], 505,
    ),
    _spec(
        'gst-calculator', 'GST Calculator',
        'Add or remove GST from a price.',
        'tax', 'fa-solid fa-percent',
        [_inr('amount', 'Amount', 10000, 1, 10000000, 1),
         _pct('gst_rate', 'GST rate', 18, 0, 28, 0.5),
         _radio('mode', 'Amount is', 'exclusive', [
             {'value': 'exclusive', 'label': 'Before GST'},
             {'value': 'inclusive', 'label': 'Includes GST'},
         ])],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'gst_amount', 'label': 'GST amount'},
            'rows': [
                {'key': 'base_amount', 'label': 'Taxable value'},
                {'key': 'total', 'label': 'Price with GST'},
            ],
            'period_toggle': False,
        }, [], 510,
    ),
    _spec(
        'inflation-calculator', 'Inflation Calculator',
        'Estimate how much today’s expense will cost in the future.',
        'planning', 'fa-solid fa-arrow-up-right-dots',
        [_inr('current_amount', 'Today’s amount', 100000, 1000, 10000000, 1000),
         _yrs('years', 'Years from now', 20, 1, 50),
         _pct('inflation_rate', 'Inflation rate (p.a.)', 6, 1, 15, 0.5)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'current_amount', 'label': 'Today', 'color': BLUE},
                {'key': 'extra_needed', 'label': 'Inflation impact', 'color': RED},
            ],
            'primary': {'key': 'future_cost', 'label': 'Future cost'},
            'rows': [
                {'key': 'current_amount', 'label': 'Today’s amount'},
                {'key': 'extra_needed', 'label': 'Extra needed'},
            ],
            'period_toggle': False,
        },
        _faq(('What inflation rate should I use?',
              'Long-term India CPI often sits around 4–6%. Education and healthcare can run higher.')),
        600,
    ),
    _spec(
        'cost-of-delay-calculator', 'Cost of Delay Calculator',
        'See how waiting to start an SIP shrinks your corpus.',
        'planning', 'fa-solid fa-hourglass-half',
        [_inr('monthly_amount', 'Monthly SIP', 5000, 500, 200000, 500),
         _yrs('years', 'Total horizon', 20, 5, 40),
         _yrs('delay_years', 'Years delayed', 5, 1, 15),
         _pct('annual_rate', 'Expected return (p.a.)', 12, 1, 30)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'delayed_value', 'label': 'If you wait', 'color': SLATE},
                {'key': 'cost', 'label': 'Cost of delay', 'color': RED},
            ],
            'primary': {'key': 'cost', 'label': 'You miss out on'},
            'rows': [
                {'key': 'start_now', 'label': 'Corpus if you start now'},
                {'key': 'delayed_value', 'label': 'Corpus if you wait'},
            ],
            'period_toggle': False,
        }, [], 605,
    ),
    _spec(
        'power-of-compounding-calculator', 'Power of Compounding',
        'Visualise how time and rate multiply a regular investment.',
        'planning', 'fa-solid fa-seedling',
        [_inr('monthly_amount', 'Monthly investment', 5000, 500, 200000, 500),
         _yrs('years', 'Period', 20, 1, 40),
         _pct('annual_rate', 'Return (p.a.)', 12, 1, 30)],
        _DONUT, [], 610, engine='sip-calculator',
    ),
    _spec(
        'future-value-calculator', 'Future Value Calculator',
        'Calculate the future value of money at a given rate.',
        'planning', 'fa-solid fa-forward',
        [_inr('amount', 'Present amount', 100000, 1000, 10000000, 1000),
         _yrs('years', 'Period', 10, 1, 40),
         _pct('annual_rate', 'Rate (p.a.)', 8, 1, 20)],
        _DONUT, [], 615, engine='lumpsum-calculator',
    ),
    _spec(
        'increasing-contribution-calculator', 'Increasing Contribution Calculator',
        'Model contributions that rise each year toward a goal.',
        'planning', 'fa-solid fa-stairs',
        [_inr('monthly_amount', 'Starting contribution', 5000, 500, 200000, 500),
         _yrs('years', 'Period', 15, 1, 40),
         _pct('annual_rate', 'Return (p.a.)', 10, 1, 20),
         _pct('step_up_percent', 'Yearly increase', 5, 0, 30, 1)],
        _DONUT, [], 620, engine='step-up-sip-calculator',
    ),
    _spec(
        'net-worth-calculator', 'Net Worth Calculator',
        'Add assets and subtract liabilities for a net-worth snapshot.',
        'planning', 'fa-solid fa-scale-balanced',
        [_inr('assets', 'Total assets', 5000000, 0, 100000000, 50000),
         _inr('liabilities', 'Total liabilities', 1500000, 0, 100000000, 50000)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'net_worth', 'label': 'Net worth', 'color': GREEN},
                {'key': 'liabilities', 'label': 'Liabilities', 'color': RED},
            ],
            'primary': {'key': 'net_worth', 'label': 'Net worth'},
            'rows': [
                {'key': 'assets', 'label': 'Assets'},
                {'key': 'liabilities', 'label': 'Liabilities'},
            ],
            'period_toggle': False,
        }, [], 625,
    ),
    _spec(
        'asset-allocation-calculator', 'Asset Allocation',
        'Educational split across equity, debt and other assets by age.',
        'planning', 'fa-solid fa-chart-pie',
        [_yrs('age', 'Your age', 30, 18, 70),
         _inr('amount', 'Investable surplus', 100000, 10000, 10000000, 5000)],
        {
            'chart': 'donut',
            'chart_slices': [
                {'key': 'equity', 'label': 'Equity', 'color': BLUE},
                {'key': 'debt', 'label': 'Debt', 'color': GREEN},
                {'key': 'other', 'label': 'Gold / other', 'color': AMBER},
            ],
            'primary': {'key': 'equity', 'label': 'Equity allocation'},
            'rows': [
                {'key': 'equity', 'label': 'Equity'},
                {'key': 'debt', 'label': 'Debt'},
                {'key': 'other', 'label': 'Gold / other'},
            ],
            'period_toggle': False,
        }, [], 630,
    ),
    _spec(
        'present-value-calculator', 'Present Value Calculator',
        'Discount a future amount back to today’s rupees.',
        'planning', 'fa-solid fa-clock-rotate-left',
        [_inr('future_amount', 'Future amount', 1000000, 1000, 50000000, 1000),
         _yrs('years', 'Years from now', 10, 1, 40),
         _pct('annual_rate', 'Discount rate (p.a.)', 8, 1, 20)],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'present_value', 'label': 'Present value'},
            'rows': [
                {'key': 'future_amount', 'label': 'Future amount'},
                {'key': 'discount', 'label': 'Discounted away'},
            ],
            'period_toggle': False,
        }, [], 635,
    ),
    _spec(
        'bmi-calculator', 'BMI Calculator',
        'Body mass index from height and weight.',
        'fitness', 'fa-solid fa-weight-scale',
        [_num('weight_kg', 'Weight', 70, 30, 200, 0.5, ' kg', 'kg'),
         _num('height_cm', 'Height', 170, 120, 220, 0.5, ' cm', 'cm')],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'bmi', 'label': 'BMI', 'format': 'number'},
            'rows': [
                {'key': 'category', 'label': 'Category', 'format': 'text'},
                {'key': 'weight_kg', 'label': 'Weight', 'format': 'kg'},
            ],
            'period_toggle': False,
        },
        _faq(('Is BMI a diagnosis?', 'No. It is a screening number. Muscle mass, age and health conditions matter.')),
        700, disclaimer=FITNESS_DISCLAIMER,
        meta_description='BMI calculator. Check body mass index from height and weight.',
    ),
    _spec(
        'ideal-weight-calculator', 'Ideal Weight Calculator',
        'Devine-formula ideal body weight from height and gender.',
        'fitness', 'fa-solid fa-person',
        [_num('height_cm', 'Height', 170, 140, 210, 0.5, ' cm', 'cm'), _GENDER],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'ideal_weight', 'label': 'Ideal weight', 'format': 'kg'},
            'rows': [{'key': 'height_cm', 'label': 'Height', 'format': 'cm'}],
            'period_toggle': False,
        }, [], 705, disclaimer=FITNESS_DISCLAIMER,
    ),
    _spec(
        'bmr-calculator', 'BMR Calculator',
        'Basal metabolic rate with the Mifflin-St Jeor equation.',
        'fitness', 'fa-solid fa-fire',
        [_num('weight_kg', 'Weight', 70, 30, 200, 0.5, ' kg', 'kg'),
         _num('height_cm', 'Height', 170, 120, 220, 0.5, ' cm', 'cm'),
         _yrs('age', 'Age', 30, 15, 80), _GENDER],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'bmr', 'label': 'BMR', 'format': 'kcal'},
            'rows': [],
            'period_toggle': False,
        }, [], 710, disclaimer=FITNESS_DISCLAIMER,
    ),
    _spec(
        'calorie-calculator', 'Calorie Calculator',
        'Daily calorie need from BMR and activity level.',
        'fitness', 'fa-solid fa-utensils',
        [_num('weight_kg', 'Weight', 70, 30, 200, 0.5, ' kg', 'kg'),
         _num('height_cm', 'Height', 170, 120, 220, 0.5, ' cm', 'cm'),
         _yrs('age', 'Age', 30, 15, 80), _GENDER,
         _select('activity', 'Activity', 'moderate', [
             {'value': 'sedentary', 'label': 'Sedentary'},
             {'value': 'light', 'label': 'Light'},
             {'value': 'moderate', 'label': 'Moderate'},
             {'value': 'active', 'label': 'Active'},
             {'value': 'very_active', 'label': 'Very active'},
         ])],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'calories', 'label': 'Maintenance calories', 'format': 'kcal'},
            'rows': [
                {'key': 'bmr', 'label': 'BMR', 'format': 'kcal'},
                {'key': 'cut', 'label': 'Cut (~500 kcal)', 'format': 'kcal'},
                {'key': 'bulk', 'label': 'Bulk (~+300 kcal)', 'format': 'kcal'},
            ],
            'period_toggle': False,
        }, [], 715, disclaimer=FITNESS_DISCLAIMER,
    ),
    _spec(
        'body-fat-calculator', 'Body Fat Calculator',
        'US Navy-method body-fat estimate from circumferences.',
        'fitness', 'fa-solid fa-percent',
        [_num('height_cm', 'Height', 170, 120, 220, 0.5, ' cm', 'cm'),
         _num('waist_cm', 'Waist', 80, 50, 160, 0.5, ' cm', 'cm'),
         _num('neck_cm', 'Neck', 38, 20, 60, 0.5, ' cm', 'cm'),
         _num('hip_cm', 'Hip (women)', 95, 50, 160, 0.5, ' cm', 'cm'),
         _GENDER],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'body_fat', 'label': 'Body fat', 'format': 'percent'},
            'rows': [],
            'period_toggle': False,
        }, [], 720, disclaimer=FITNESS_DISCLAIMER,
    ),
    _spec(
        'macro-calculator', 'Macro Calculator',
        'Split daily calories into protein, carbs and fat.',
        'fitness', 'fa-solid fa-bowl-food',
        [_num('calories', 'Daily calories', 2000, 1000, 5000, 50, ' kcal', 'kcal'),
         _select('goal', 'Goal', 'maintain', [
             {'value': 'cut', 'label': 'Cut'},
             {'value': 'maintain', 'label': 'Maintain'},
             {'value': 'bulk', 'label': 'Bulk'},
         ])],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'protein', 'label': 'Protein (g)', 'format': 'number'},
            'rows': [
                {'key': 'carbs', 'label': 'Carbs (g)', 'format': 'number'},
                {'key': 'fat', 'label': 'Fat (g)', 'format': 'number'},
                {'key': 'calories', 'label': 'Calories', 'format': 'kcal'},
            ],
            'period_toggle': False,
        }, [], 725, disclaimer=FITNESS_DISCLAIMER,
    ),
    _spec(
        'ovulation-calculator', 'Ovulation Calculator',
        'Estimate ovulation and fertile window from last period.',
        'fitness', 'fa-solid fa-calendar-day',
        [_date('lmp', 'First day of last period'),
         _num('cycle_length', 'Cycle length', 28, 21, 40, 1, ' days', 'number')],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'ovulation_date', 'label': 'Ovulation', 'format': 'date'},
            'rows': [
                {'key': 'fertile_start', 'label': 'Fertile from', 'format': 'date'},
                {'key': 'fertile_end', 'label': 'Fertile until', 'format': 'date'},
                {'key': 'next_period', 'label': 'Next period', 'format': 'date'},
            ],
            'period_toggle': False,
        },
        _faq(('Is this a fertility diagnosis?', 'No. Cycle length varies. Use it as a calendar aid only.')),
        730, disclaimer=FITNESS_DISCLAIMER,
    ),
    _spec(
        'pregnancy-calculator', 'Pregnancy Calculator',
        'Estimate gestational weeks and trimester from last period.',
        'fitness', 'fa-solid fa-baby',
        [_date('lmp', 'First day of last period')],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'weeks', 'label': 'Weeks pregnant', 'format': 'number'},
            'rows': [
                {'key': 'trimester', 'label': 'Trimester', 'format': 'number'},
                {'key': 'due_date', 'label': 'Due date', 'format': 'date'},
            ],
            'period_toggle': False,
        }, [], 735, disclaimer=FITNESS_DISCLAIMER,
    ),
    _spec(
        'pregnancy-conception-calculator', 'Pregnancy Conception Calculator',
        'Estimate conception date from last period and cycle length.',
        'fitness', 'fa-solid fa-heart',
        [_date('lmp', 'First day of last period'),
         _num('cycle_length', 'Cycle length', 28, 21, 40, 1, ' days', 'number')],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'conception_date', 'label': 'Est. conception', 'format': 'date'},
            'rows': [{'key': 'due_date', 'label': 'Due date', 'format': 'date'}],
            'period_toggle': False,
        }, [], 740, disclaimer=FITNESS_DISCLAIMER,
    ),
    _spec(
        'pregnancy-weight-gain-calculator', 'Pregnancy Weight Gain Calculator',
        'IOM-style recommended weight gain by week and starting BMI.',
        'fitness', 'fa-solid fa-weight-hanging',
        [_num('pre_weight', 'Pre-pregnancy weight', 60, 35, 150, 0.5, ' kg', 'kg'),
         _num('height_cm', 'Height', 160, 140, 190, 0.5, ' cm', 'cm'),
         _num('week', 'Pregnancy week', 20, 1, 40, 1, '', 'number')],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'recommended_gain', 'label': 'Gain so far (kg)', 'format': 'kg'},
            'rows': [
                {'key': 'total_gain', 'label': 'Full-term target (kg)', 'format': 'kg'},
                {'key': 'bmi', 'label': 'Starting BMI', 'format': 'number'},
            ],
            'period_toggle': False,
        }, [], 745, disclaimer=FITNESS_DISCLAIMER,
    ),
    _spec(
        'due-date-calculator', 'Due Date Calculator',
        'Naegele’s rule: last period plus 280 days.',
        'fitness', 'fa-solid fa-calendar-check',
        [_date('lmp', 'First day of last period')],
        {
            'chart': 'none', 'chart_slices': [],
            'primary': {'key': 'due_date', 'label': 'Due date', 'format': 'date'},
            'rows': [{'key': 'conception_date', 'label': 'Est. conception', 'format': 'date'}],
            'period_toggle': False,
        }, [], 750, disclaimer=FITNESS_DISCLAIMER,
    ),
]

CALCULATOR_BY_SLUG = {item['slug']: item for item in CALCULATORS}


def get_spec(slug):
    resolved = SLUG_REDIRECTS.get(slug, slug)
    spec = CALCULATOR_BY_SLUG.get(resolved)
    if not spec:
        return None
    return deepcopy(spec)


def engine_slug_for(slug):
    spec = CALCULATOR_BY_SLUG.get(SLUG_REDIRECTS.get(slug, slug))
    if not spec:
        return slug
    return spec.get('engine') or spec['slug']
