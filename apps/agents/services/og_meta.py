"""Open Graph context for agent profile / card share pages."""
from apps.agents.services.og_urls import agent_og_image_absolute_url, build_og_absolute_url

_SEGMENT_LABELS = {
    'health': 'Health',
    'life': 'Life',
    'motor': 'Motor',
    'sme': 'SME',
}


def _segment_labels(agent):
    try:
        raw = list(getattr(agent, 'ordered_insurance_segments', None) or [])
    except Exception:
        raw = []
    labels = []
    for item in raw:
        key = str(item or '').strip().lower()
        if not key:
            continue
        label = _SEGMENT_LABELS.get(key, key.replace('_', ' ').title())
        if label not in labels:
            labels.append(label)
    return labels


def profile_og_context(request, agent, *, display_name=None):
    """
    WhatsApp / Facebook need non-empty og:title and og:description.
    Never use zero-width or empty description — that breaks image previews.
    """
    name = (display_name or getattr(agent, 'fullname', None) or 'Insurance Advisor').strip()
    profile = None
    try:
        profile = agent.get_primary_profile() if hasattr(agent, 'get_primary_profile') else getattr(agent, 'profile', None)
    except Exception:
        profile = getattr(agent, 'profile', None)

    exp = 0
    try:
        exp = int(getattr(agent, 'experience_years', 0) or 0)
    except (TypeError, ValueError):
        exp = 0
    if profile:
        try:
            profile_exp = int(getattr(profile, 'experience_years', 0) or 0)
        except (TypeError, ValueError):
            profile_exp = 0
        if profile_exp:
            exp = profile_exp

    parts = []
    if exp:
        parts.append(f'{exp} yrs exp')
    seg_labels = _segment_labels(agent)
    if seg_labels:
        parts.append(', '.join(seg_labels))

    city = ''
    try:
        from apps.agents.services.agent_city import resolve_agent_city
        city = (resolve_agent_city(agent) or '').strip()
    except Exception:
        city = ''

    licensed = bool(profile and (getattr(profile, 'license_number', None) or getattr(profile, 'arn_number', None)))
    role = 'a licensed insurance advisor' if licensed else 'an insurance advisor'

    title = f'{name} | PadosiAgent'
    detail = ' · '.join(parts)
    location = f' in {city}' if city else ''
    description = f'Connect with {name}'
    if detail:
        description += f' — {detail}'
    description += f', {role}{location} on PadosiAgent.'

    return {
        'og_share_title': title,
        'og_share_description': description,
        'og_image_absolute_url': agent_og_image_absolute_url(request, agent.id),
        'og_page_absolute_url': build_og_absolute_url(request, request.get_full_path()),
    }
