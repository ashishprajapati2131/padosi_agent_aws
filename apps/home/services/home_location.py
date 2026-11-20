"""Read-only location label for homepage headings (no session writes)."""

import re

from apps.home.services.distance import EXACT_PINCODE_COORDS, DistanceService

_DEFAULT_PIN_RANK = '380001'
_NEUTRAL_LABEL = 'your area'

_PIN_RE = re.compile(r'^[1-9]\d{5}$')


def has_homepage_location(request) -> bool:
    """True when user has set PIN, GPS, text location, or detected_area in session."""
    if not request:
        return False
    session = request.session
    if (session.get('last_pincode') or '').strip():
        return True
    if (session.get('detected_area') or '').strip():
        return True
    if (session.get('last_location') or '').strip():
        return True
    if (session.get('last_lat') or '').strip() and (session.get('last_lng') or '').strip():
        return True
    return False


def get_homepage_location_label(request):
    """
    Return (display_label, pincode) for homepage copy.
    Without user location, label is neutral — never a default city name.
    """
    if not has_homepage_location(request):
        return _NEUTRAL_LABEL, ''

    detected = (request.session.get('detected_area') or '').strip()
    if detected and not _PIN_RE.match(detected) and not detected.startswith('PIN:'):
        return detected, (request.session.get('last_pincode') or '').strip()

    pincode = (request.session.get('last_pincode') or '').strip()
    if _PIN_RE.match(pincode):
        exact = DistanceService.get_precise_pincode_coordinates(pincode)
        if exact:
            office = exact.get('office_name') or ''
            district = exact.get('district') or ''
            label = f"{office}, {district}".strip(', ')
            if label:
                return label, pincode
        return f"PIN: {pincode}", pincode

    location = (request.session.get('last_location') or '').strip()
    if location:
        return location, ''

    if detected:
        return detected, pincode

    return _NEUTRAL_LABEL, ''


def resolve_home_coordinates(request, *, allow_default=False):
    """
    Lat/lng and pincode for ranking.
    When allow_default is False and user has no location, returns (None, None, '').
    """
    if not request:
        if allow_default:
            exact = EXACT_PINCODE_COORDS[_DEFAULT_PIN_RANK]
            return float(exact['lat']), float(exact['lng']), _DEFAULT_PIN_RANK
        return None, None, ''

    pincode = (request.session.get('last_pincode') or '').strip()
    lat_s = (request.session.get('last_lat') or '').strip()
    lng_s = (request.session.get('last_lng') or '').strip()

    if lat_s and lng_s:
        try:
            return float(lat_s), float(lng_s), pincode
        except (TypeError, ValueError):
            pass

    if _PIN_RE.match(pincode):
        exact = DistanceService.get_precise_pincode_coordinates(pincode)
        if not exact:
            exact = EXACT_PINCODE_COORDS.get(pincode) or EXACT_PINCODE_COORDS.get(_DEFAULT_PIN_RANK)
        if exact:
            return float(exact['lat']), float(exact['lng']), pincode

    if not has_homepage_location(request):
        if allow_default:
            exact = EXACT_PINCODE_COORDS[_DEFAULT_PIN_RANK]
            return float(exact['lat']), float(exact['lng']), _DEFAULT_PIN_RANK
        return None, None, ''

    if allow_default:
        exact = EXACT_PINCODE_COORDS[_DEFAULT_PIN_RANK]
        return float(exact['lat']), float(exact['lng']), _DEFAULT_PIN_RANK

    return None, None, ''


def invalidate_homepage_agent_caches(pincode=''):
    """Clear homepage agent list caches after location change."""
    from django.core.cache import cache

    keys = [
        f'homepage_matching_v1:{pincode or "default"}',
        f'homepage_matching_v2:{pincode or "none"}',
        f'homepage_matching_v2:{pincode or "default"}',
        f'homepage_matching_v3:{pincode or "none"}',
        f'homepage_matching_v3:{pincode or "default"}',
        f'homepage_top_rated_v1:{pincode or "default"}',
        f'homepage_top_rated_v2:{pincode or "default"}',
        f'homepage_top_rated_v3:{pincode or "default"}',
        f'homepage_top_rated_v4:{pincode or "default"}',
        f'homepage_segments_v2:{pincode or "none"}',
        f'homepage_segments_v3:{pincode or "none"}',
        'homepage_segments_v2:none',
        'homepage_segments_v3:none',
        f'homepage_matching_v1:380001',
        f'homepage_matching_v2:380001',
        f'homepage_matching_v3:380001',
        f'homepage_top_rated_v1:380001',
        f'homepage_top_rated_v2:380001',
        f'homepage_top_rated_v3:380001',
        f'homepage_top_rated_v4:380001',
    ]
    seen = set()
    for key in keys:
        if key not in seen:
            seen.add(key)
            cache.delete(key)