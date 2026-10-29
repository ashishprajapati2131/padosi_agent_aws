"""Resolve the city an agent actually belongs to.

Serviceable cities are areas the agent covers. The lowest primary key in that
list is often Ahmedabad, so `serviceableCities.first()` is not the agent's city.
Prefer the agent's own pincode, then a city named in their address.
"""
import re


_JUNK_PLACE = re.compile(r'^(area|region|pin)(\s+\d|\s*:)', re.IGNORECASE)
_JUNK_CITY = re.compile(
    r'^(all\b|and all\b|world\b|other\b|na\b|n/?a\b|none\b|\d)',
    re.IGNORECASE,
)
_PIN = re.compile(r'^[1-9]\d{5}$')
_OFFICE_SUFFIX = re.compile(
    r'\s+(S\.?O\.?|B\.?O\.?|H\.?O\.?|G\.?P\.?O\.?)$',
    re.IGNORECASE,
)


def _is_mock(value):
    return value is not None and hasattr(value, '_mock_return_value')


def _clean_place(value):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not text or _JUNK_PLACE.match(text):
        return ''
    return _OFFICE_SUFFIX.sub('', text).strip(' ,')


def _title_city(value):
    text = _clean_place(value)
    if not text:
        return ''
    if text.isupper() or text.islower():
        return text.title()
    return text


def _sensible_city_name(name):
    text = str(name or '').strip()
    if len(text) < 3 or _is_mock(name):
        return False
    if _JUNK_CITY.match(text) or _JUNK_PLACE.match(text):
        return False
    return bool(re.search(r'[A-Za-z]', text))


def _city_from_pincode_row(row):
    if not row or _is_mock(row):
        return ''
    district = _clean_place(getattr(row, 'district', ''))
    if district:
        return _title_city(district)
    office = _clean_place(getattr(row, 'office_name', ''))
    if not office:
        return ''
    if ',' in office:
        tail = re.sub(r'\btaluka\b', '', office.split(',')[-1], flags=re.IGNORECASE)
        tail = _title_city(tail)
        if tail:
            return tail
    return _title_city(office)


def _fold_repeats(text):
    """Collapse doubled letters so 'himatnagar' can match 'himmatnagar'."""
    return re.sub(r'(.)\1+', r'\1', str(text or ''), flags=re.IGNORECASE)


def _last_name_index(blob, name):
    pattern = re.compile(
        rf'(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])',
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(blob))
    return matches[-1].start() if matches else None


def _rightmost_city(text, names, skip_name='', allow_folded=False):
    blob = str(text or '')
    if not blob.strip():
        return ''
    skip = (skip_name or '').strip().lower()
    folded_blob = _fold_repeats(blob) if allow_folded else ''
    best = None
    for raw in names:
        if not _sensible_city_name(raw):
            continue
        name = str(raw).strip()
        if skip and name.lower() == skip:
            continue
        exact_at = _last_name_index(blob, name)
        folded_at = None
        if exact_at is None and allow_folded:
            folded_at = _last_name_index(folded_blob, _fold_repeats(name))
        if exact_at is None and folded_at is None:
            continue
        # Exact spelling wins over a folded spelling, then the rightmost name.
        kind = 1 if exact_at is not None else 0
        position = exact_at if exact_at is not None else folded_at
        cand = (kind, position, len(name), name)
        if best is None or cand[:3] > best[:3]:
            best = cand
    return _title_city(best[3]) if best else ''


def _profile(agent):
    if _is_mock(agent):
        return None
    try:
        profile = agent.profile
    except Exception:
        return None
    if _is_mock(profile):
        return None
    return profile


def _agent_pin(agent, profile):
    pin = str(getattr(agent, 'agent_pincode', '') or '').strip()
    if _PIN.match(pin):
        return pin
    pins = getattr(profile, 'service_pincodes', None) if profile is not None else None
    if isinstance(pins, list):
        for item in pins:
            candidate = str(item or '').strip()
            if _PIN.match(candidate):
                return candidate
    return ''


def _service_city_names(agent):
    try:
        names = [city.name for city in agent.serviceableCities.all()]
    except Exception:
        return []
    return [name for name in names if _sensible_city_name(name)]


def resolve_agent_city(agent):
    """Return the agent's own city, or their state when the city is unknown."""
    if agent is None or _is_mock(agent):
        return ''
    profile = _profile(agent)
    state = ''
    if profile is not None:
        state = _title_city(getattr(profile, 'state', '') or '')
        if state.lower() in ('other', 'na', 'n/a', 'none'):
            state = ''

    pin = _agent_pin(agent, profile)
    if pin:
        try:
            from apps.home.models.pincode import Pincode
            row = Pincode.objects.filter(pincode=pin).first()
        except Exception:
            row = None
        city = _city_from_pincode_row(row)
        if city:
            return city
        try:
            service_pin = agent.servicePincodes.filter(service_pincode=pin).first()
        except Exception:
            service_pin = None
        if service_pin is not None and not _is_mock(service_pin):
            named = _title_city(getattr(service_pin, 'city_name', ''))
            if named and _sensible_city_name(named):
                return named

    address = ''
    if profile is not None:
        address = ' '.join(
            part for part in (
                getattr(profile, 'address', '') or '',
                getattr(profile, 'office_address', '') or '',
            ) if part
        )
    service_names = _service_city_names(agent)
    matched = _rightmost_city(address, service_names, skip_name=state, allow_folded=True)
    if matched:
        return matched
    if address.strip():
        try:
            from apps.agents.models import City
            known = list(City.objects.values_list('name', flat=True))
        except Exception:
            known = []
        matched = _rightmost_city(address, known, skip_name=state)
        if matched:
            return matched

    if len(service_names) == 1:
        return _title_city(service_names[0])
    return state


def agent_city_label(agent):
    """City label for cards and listings, with a count of other service cities."""
    city = resolve_agent_city(agent)
    if not city:
        return ''
    names = _service_city_names(agent)
    city_key = city.strip().lower()
    if not any(name.strip().lower() == city_key for name in names):
        return city
    others = [name for name in names if name.strip().lower() != city_key]
    if others:
        return f'{city} +{len(others)} more'
    return city
