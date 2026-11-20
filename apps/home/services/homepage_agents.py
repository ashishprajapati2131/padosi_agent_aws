"""Homepage agent lists — cached, isolated from find-agents view."""

import logging

from django.core.cache import cache

from apps.agents.services.license_status import is_irdai_license_active
from apps.home.services.agent_filters import apply_location_text_filter, listed_agents_queryset
from apps.home.services.distance import apply_search_proximity
from apps.home.services.home_location import has_homepage_location, resolve_home_coordinates
from apps.home.services.homepage import DEFAULT_SEGMENT_SHOWCASE
from apps.home.services.matching import assign_match_percents

logger = logging.getLogger(__name__)

SEGMENT_KEYS = ('health', 'life', 'motor', 'sme', 'mutual_fund')

SEGMENT_LABELS = {
    'health': 'Health Insurance',
    'life': 'Life Insurance',
    'motor': 'Motor Insurance',
    'sme': 'SME Insurance',
    'mutual_fund': 'Mutual Fund',
}

_SEGMENT_META = {item['key']: item for item in DEFAULT_SEGMENT_SHOWCASE}


def _showcase_fields(segment_key):
    meta = _SEGMENT_META.get(segment_key, {})
    services = meta.get('services') or meta.get('tags') or []
    return {
        'image': meta.get('image', 'img/home/segment-health.png'),
        'services': list(services),
        'rating_display': meta.get('rating', '4.9'),
        'experience_display': meta.get('experience', '10+ Years'),
        'customers_display': meta.get('customers', '1k+'),
        'url': meta.get('url', '/find-agents?openFilter=1'),
        'title': meta.get('title', SEGMENT_LABELS.get(segment_key, '')),
        'theme_class': meta.get('theme_class', 'hp-seg-teal'),
    }


def _agent_service_tags(agent):
    """End-service labels for matching cards (not insurance segment types)."""
    tags = []
    prefs = getattr(agent, 'leadPreferences', None)
    if prefs:
        if getattr(prefs, 'leads_new_business', False):
            tags.append('Buy')
        if getattr(prefs, 'leads_claims_support', False):
            tags.append('Claim')
        if getattr(prefs, 'leads_portfolio_analysis', False):
            tags.extend(['Port', 'Endorsement', 'Policy Review'])
    if not tags:
        tags = ['Buy', 'Claim', 'Endorsement']
    seen = []
    for t in tags:
        if t not in seen:
            seen.append(t)
    return seen[:4]


def _segment_types(agent):
    if hasattr(agent, 'ordered_insurance_segments'):
        segs = list(agent.ordered_insurance_segments or [])
        if segs:
            return set(segs)
    if hasattr(agent, 'insuranceSegments'):
        return {s.segment_type for s in agent.insuranceSegments.all() if s.segment_type}
    return set()


def agent_matches_segment(agent, segment_key: str) -> bool:
    segs = _segment_types(agent)
    profile = agent.get_primary_profile() if hasattr(agent, 'get_primary_profile') else getattr(agent, 'profile', None)
    if segment_key == 'mutual_fund':
        if profile and getattr(profile, 'arn_number', None):
            return True
        if 'investment' in segs or 'mutual_fund' in segs:
            return True
        if profile and getattr(profile, 'normalized_investment_types', None):
            types = profile.normalized_investment_types
            if types:
                return True
        return False
    return segment_key in segs


def _format_clients(clients):
    try:
        clients = int(clients or 0)
    except (TypeError, ValueError):
        clients = 0
    if clients >= 1000:
        return f"{clients / 1000:.1f}k+".replace('.0k', 'k')
    if clients:
        return f"{clients}+"
    return '—'


def _contact_links(profile):
    whatsapp = getattr(profile, 'whatsapp', '') or '' if profile else ''
    phone = ''
    if profile:
        phone = getattr(profile, 'phone', '') or getattr(profile, 'mobile', '') or ''
    wa_link = ''
    digits = ''.join(c for c in str(whatsapp) if c.isdigit())
    if len(digits) >= 10:
        if len(digits) == 10:
            digits = '91' + digits
        wa_link = f"https://wa.me/{digits}"
    tel_link = ''
    pd = ''.join(c for c in str(phone) if c.isdigit())
    if len(pd) >= 10:
        tel_link = f"tel:+{pd if pd.startswith('91') else '91' + pd[-10:]}"
    return tel_link, wa_link


def serialize_segment_agent(agent, segment_key):
    profile = agent.get_primary_profile() if hasattr(agent, 'get_primary_profile') else getattr(agent, 'profile', None)
    perf = getattr(agent, 'performanceStats', None)
    slug = getattr(profile, 'slug', None) if profile else None
    state = getattr(profile, 'state_code', None) or 'gj'
    photo = getattr(profile, 'profile_photo_url', '') if profile else ''

    city = getattr(agent, 'agent_city_display', None) or ''
    distance = getattr(agent, 'distance', None)
    if distance is not None and distance != 999999:
        if distance < 1:
            dist_display = 'Nearby'
        else:
            dist_display = f"{float(distance):.1f} km"
    else:
        dist_display = ''

    exp = getattr(agent, 'experience_years', None) or 0
    rating = float(getattr(agent, 'average_rating', 0) or 0)
    match_pct = int(getattr(agent, 'match_percent', None) or getattr(agent, 'calculated_match_percent', None) or 85)

    claims = 0
    if perf:
        for attr in ('claims_processed', 'claims_settled'):
            val = getattr(perf, attr, None)
            if val is not None and str(val).isdigit():
                claims = int(val)
                break

    tel_link, wa_link = _contact_links(profile)
    license_line = ''
    if segment_key == 'mutual_fund' and profile and profile.arn_number:
        license_line = f"ARN {profile.arn_number}"
    elif profile and profile.license_number:
        license_line = f"IRDAI {profile.license_number}"

    location_line = city or 'Your area'
    if dist_display:
        location_line = f"{location_line} · {dist_display}"

    return {
        'id': agent.id,
        'name': getattr(agent, 'display_name', None) or agent.fullname,
        'photo': photo,
        'is_verified': bool(getattr(agent, 'is_verified_agent', False)),
        'location_line': location_line,
        'match_percent': match_pct,
        'rating': round(rating, 1) if rating else 0.0,
        'experience_display': f"{int(exp)} yrs" if exp else '—',
        'clients_display': _format_clients(getattr(agent, 'client_base', 0)),
        'claims_display': f"{claims}+" if claims else '—',
        'license_line': license_line,
        'profile_url': f"/{state}/{slug}/" if slug else '/find-agents?openFilter=1',
        'whatsapp_url': wa_link,
        'phone_url': tel_link,
        'segment_key': segment_key,
        'segment_label': SEGMENT_LABELS.get(segment_key, 'Insurance'),
    }


def _serialize_agent(agent):
    """Compact dict for matching / top-rated rows."""
    seg_key = 'health'
    for key in SEGMENT_KEYS:
        if agent_matches_segment(agent, key):
            seg_key = key
            break
    data = serialize_segment_agent(agent, seg_key)
    data['service_tags'] = _agent_service_tags(agent)
    data['city'] = getattr(agent, 'agent_city_display', None) or 'Your area'
    data['is_trusted'] = bool(getattr(agent, 'is_trusted', False) or getattr(agent, 'is_verified_agent', False))
    data['review_count'] = int(getattr(agent, 'review_count', 0) or getattr(agent, 'total_reviews', 0) or 0)
    return data


def _fetch_ranked_agents(request, limit=120, *, allow_default=False):
    user_lat, user_lng, pincode = resolve_home_coordinates(request, allow_default=allow_default)
    if user_lat is None and user_lng is None and not pincode and not allow_default:
        return []
    query = listed_agents_queryset().select_related(
        'leadPreferences', 'profile', 'performanceStats',
    ).prefetch_related('insuranceSegments', 'reviews', 'servicePincodes')
    query = apply_location_text_filter(query, '', pincode=pincode or '', has_coords=bool(user_lat))
    agents = list(query[:limit])
    agents = apply_search_proximity(
        agents, user_lat, user_lng, search_pincode=pincode or None, keep_outside_radius=True,
    )
    assign_match_percents(agents)
    agents.sort(
        key=lambda a: (
            0 if getattr(a, 'is_nearby', False) else 1,
            a.distance if getattr(a, 'distance', None) is not None else 999999,
            -(getattr(a, 'padosi_smart_rank', 0) or 0),
            -(float(getattr(a, 'average_rating', 0) or 0)),
        ),
    )
    return agents


def _pick_top_per_segment(agents, used_ids, per_segment=3):
    """Pick up to per_segment agents per segment with global de-dupe across segments."""
    featured = {}
    for segment_key in SEGMENT_KEYS:
        showcase = _showcase_fields(segment_key)
        slot = {
            'key': segment_key,
            'mode': 'empty',
            'agent': None,
            'agents': [],
            **showcase,
        }
        for agent in agents:
            if agent.id in used_ids:
                continue
            if not agent_matches_segment(agent, segment_key):
                continue
            row = serialize_segment_agent(agent, segment_key)
            slot['agents'].append(row)
            used_ids.add(agent.id)
            if len(slot['agents']) >= per_segment:
                break
        if slot['agents']:
            slot['mode'] = 'live'
            slot['agent'] = slot['agents'][0]
        featured[segment_key] = slot
    return [featured[k] for k in SEGMENT_KEYS]


def get_home_segment_experts(request):
    if not has_homepage_location(request):
        slots = []
        for segment_key in SEGMENT_KEYS:
            slots.append({
                'key': segment_key,
                'mode': 'placeholder',
                'agent': None,
                'agents': [],
                **_showcase_fields(segment_key),
            })
        return slots, 'placeholder'

    pincode = resolve_home_coordinates(request, allow_default=False)[2] or 'none'
    cache_key = f'homepage_segments_v3:{pincode}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        agents = _fetch_ranked_agents(request, limit=200, allow_default=False)
        used_ids = set()
        slots = _pick_top_per_segment(agents, used_ids, per_segment=3)
    except Exception:
        logger.exception('homepage segment experts failed')
        slots = _pick_top_per_segment([], set(), per_segment=3)

    result = (slots, 'live')
    cache.set(cache_key, result, 900)
    return result


def get_segment_compare_agents(request, segment_key, limit=3):
    if segment_key not in SEGMENT_KEYS or not has_homepage_location(request):
        return []
    # Prefer already-picked stack from cache order: re-rank fresh for this segment only
    agents = _fetch_ranked_agents(request, limit=200, allow_default=False)
    picked = []
    for agent in agents:
        if not agent_matches_segment(agent, segment_key):
            continue
        picked.append(agent)
        if len(picked) >= limit:
            break
    return picked


def _pick_diverse(agents, limit, per_segment=2):
    picked = []
    counts = {}
    for agent in agents:
        seg = None
        for key in SEGMENT_KEYS:
            if agent_matches_segment(agent, key):
                seg = key
                break
        if not seg:
            seg = 'health'
        if counts.get(seg, 0) >= per_segment:
            continue
        picked.append(_serialize_agent(agent))
        counts[seg] = counts.get(seg, 0) + 1
        if len(picked) >= limit:
            break
    if len(picked) < limit:
        for agent in agents:
            if any(p['id'] == agent.id for p in picked):
                continue
            picked.append(_serialize_agent(agent))
            if len(picked) >= limit:
                break
    return picked


def get_home_matching_experts(request, limit=8):
    if not has_homepage_location(request):
        return []
    pincode = resolve_home_coordinates(request, allow_default=False)[2] or 'none'
    cache_key = f"homepage_matching_v3:{pincode}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        agents = _fetch_ranked_agents(request, limit=limit * 3, allow_default=False)
        result = _pick_diverse(agents, limit, per_segment=2)
    except Exception:
        logger.exception('homepage matching experts query failed')
        result = []
    cache.set(cache_key, result, 900)
    return result


def get_home_top_rated_experts(request, limit=6):
    pincode = resolve_home_coordinates(request, allow_default=True)[2] or 'default'
    cache_key = f"homepage_top_rated_v4:{pincode}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        agents = _fetch_ranked_agents(request, limit=limit * 4, allow_default=True)
        agents.sort(
            key=lambda a: (
                -(float(getattr(a, 'average_rating', 0) or 0)),
                -(getattr(a, 'review_count', 0) or 0),
                -(getattr(a, 'experience_years', 0) or 0),
            ),
        )
        result = [_serialize_agent(a) for a in agents[:limit]]
    except Exception:
        logger.exception('homepage top rated query failed')
        result = []
    cache.set(cache_key, result, 900)
    return result