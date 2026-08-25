"""Find-agents directory filters.

Imported PHP agents often have no Django auth_user. Product names from the
homepage (Fire (SME), Super Top-up) also do not match stored expertise rows.
"""
import re

from django.db.models import Q

from apps.agents.models import Agent

INSURANCE_TYPE_MAPPING = {
    'Health Insurance': 'health', 'Health': 'health',
    'Life Insurance': 'life', 'Life': 'life',
    'Motor Insurance': 'motor', 'Motor': 'motor',
    'Vehicle Insurance': 'motor', 'Vehicle': 'motor',
    'SME Insurance': 'sme', 'SME': 'sme',
    'Business Insurance': 'sme', 'Business': 'sme',
    'Travel Insurance': 'travel', 'Travel': 'travel',
    'Fire Insurance': 'fire', 'Fire': 'fire',
    'Marine Insurance': 'marine', 'Marine': 'marine',
    'Liability Insurance': 'liability', 'Liability': 'liability',
    'Other General Insurance': 'other', 'Transport': 'transport',
    'Workmen Compensation': 'workmen_compensation', 'GPA / GMC': 'gpa_gmc',
    'Group Term Insurance': 'group_term', 'Cyber': 'cyber',
}

# Homepage / URL labels → find-agents circle-tile data-product
HOMEPAGE_PRODUCT_TO_TILE = {
    'fire (sme)': 'Others',
    'cyber (sme)': 'Cyber',
    'liability (sme)': 'Liability',
    'super top-up': 'Top-up',
}

# Tile / URL value → product_name values stored on agent_product_expertise
UI_PRODUCT_TO_DB_NAMES = {
    'mediclaim': ['Mediclaim'],
    'family mediclaim': ['Family Mediclaim'],
    'personal accident': ['Personal Accident'],
    'critical illness': ['Critical Illness'],
    'top-up': ['Top-up', 'Super Top-up', 'Super Top-Up'],
    'super top-up': ['Top-up', 'Super Top-up', 'Super Top-Up'],
    'hospital cash': ['Hospital Cash'],
    'private car': ['Private Car'],
    'two wheeler': ['Two Wheeler'],
    'commercial vehicle': ['Commercial Vehicle'],
    'term plan': ['Term Plan'],
    'ulip plan': ['ULIP Plan'],
    'saving plan': ['Saving Plan'],
    'pension plan': ['Pension Plan'],
    'fire': ['Fire', 'Property', 'Fire (SME)'],
    'property': ['Fire', 'Property', 'Fire (SME)'],
    'gpa/gmc': ['GPA/GMC', 'GPA / GMC'],
    'gpa / gmc': ['GPA/GMC', 'GPA / GMC'],
    'liability': ['Liability', 'Liability (SME)'],
    'cyber': ['Cyber', 'Cyber (SME)'],
}

# Named tiles that are NOT the Others bucket, keyed by segment.
# Fire sits in Others because homepage "Fire (SME)" maps to that tile.
NAMED_PRODUCTS_EXCLUDING_OTHERS = {
    'health': [
        'Mediclaim', 'Family Mediclaim', 'Personal Accident',
        'Critical Illness', 'Top-up', 'Super Top-up', 'Super Top-Up', 'Hospital Cash',
    ],
    'motor': ['Private Car', 'Two Wheeler', 'Commercial Vehicle'],
    'life': ['Term Plan', 'ULIP Plan', 'Saving Plan', 'Pension Plan'],
    'sme': ['GPA/GMC', 'GPA / GMC', 'Liability', 'Liability (SME)', 'Cyber', 'Cyber (SME)'],
}

_PIN_RE = re.compile(r'^[1-9]\d{5}$')


def listed_agents_queryset():
    """Active directory agents, including PHP imports with no auth_user FK."""
    return Agent.objects.filter(status='active').exclude(profile__is_card_visible=False)


def map_insurance_types(raw_types):
    db_types = []
    for raw in raw_types or []:
        text = (raw or '').strip()
        if not text:
            continue
        mapped = INSURANCE_TYPE_MAPPING.get(text)
        if not mapped:
            mapped = INSURANCE_TYPE_MAPPING.get(text.title())
        if not mapped:
            mapped = text.lower().replace(' insurance', '').strip()
        if mapped and mapped not in db_types:
            db_types.append(mapped)
    return db_types


def canonicalize_product_tile(raw):
    """Map homepage/URL product labels onto find-agents tile data-product values."""
    text = (raw or '').strip()
    if not text:
        return ''
    mapped = HOMEPAGE_PRODUCT_TO_TILE.get(text.lower())
    return mapped or text


def expand_product_db_names(raw):
    tile = canonicalize_product_tile(raw)
    if not tile or tile.lower() == 'others':
        return []
    return UI_PRODUCT_TO_DB_NAMES.get(tile.lower(), [tile])


def is_others_product(raw):
    tile = canonicalize_product_tile(raw)
    return tile.lower() == 'others' if tile else False


def apply_insurance_type_filter(query, insurance_types):
    db_types = map_insurance_types(insurance_types)
    if db_types:
        query = query.filter(insuranceSegments__segment_type__in=db_types).distinct()
    return query, db_types


def _iexact_name_q(names, prefix='productExpertise__product_name'):
    q = Q()
    for name in names:
        q |= Q(**{f'{prefix}__iexact': name})
    return q


def apply_insurance_product_filter(query, insurance_companies, db_types=None):
    """Match expertise rows even when homepage labels differ from stored names."""
    selected = [v for v in (insurance_companies or []) if (v or '').strip()]
    if not selected:
        return query

    others_requested = any(is_others_product(v) for v in selected)
    named = []
    for value in selected:
        named.extend(expand_product_db_names(value))

    q_company = Q()
    if named:
        q_company |= _iexact_name_q(named)

    if others_requested:
        segments = db_types or ['health', 'life', 'motor', 'sme']
        named_exclude = []
        for segment in segments:
            named_exclude.extend(NAMED_PRODUCTS_EXCLUDING_OTHERS.get(segment, []))
        q_others = Q(productExpertise__segment_type__in=segments)
        if named_exclude:
            q_others &= ~_iexact_name_q(named_exclude)
        q_company |= q_others

    if q_company and db_types and not others_requested:
        q_company &= Q(productExpertise__segment_type__in=db_types)

    if q_company:
        query = query.filter(q_company).distinct()
    return query


def apply_location_text_filter(query, location, pincode=None, has_coords=False):
    """Only apply a text location filter when GPS/pincode proximity is not in play."""
    if has_coords or _PIN_RE.match(str(pincode or '').strip()):
        return query
    location = (location or '').strip()
    if not location:
        return query

    tokens = [part.strip() for part in re.split(r'[,/|]', location) if part.strip()]
    tokens = [t for t in tokens if len(t) >= 3 and not _PIN_RE.match(t)]
    if not tokens:
        tokens = [location]

    q = Q()
    for token in tokens:
        q |= (
            Q(profile__address__icontains=token)
            | Q(profile__office_address__icontains=token)
            | Q(profile__city__icontains=token)
            | Q(profile__state__icontains=token)
            | Q(serviceableCities__name__icontains=token)
            | Q(agent_pincode__icontains=token)
        )
    return query.filter(q).distinct()
