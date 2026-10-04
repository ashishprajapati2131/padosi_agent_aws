"""
Google Review System Service.
Manages global admin configuration, plan eligibility, agent-level review configs,
and post-review nudge flows.
"""
import logging
from decimal import Decimal, InvalidOperation
from apps.home.models import SiteSetting, GoogleReviewConfig
from apps.agents.services.feature_unlock import normalize_plan_slug, PLAN_SLUGS

logger = logging.getLogger(__name__)

DEFAULT_GOOGLE_REVIEW_SYSTEM = {
    # Master switch
    'enabled': True,

    # Plan eligibility (canonical plan slugs)
    'eligible_plans': ['starter', 'professional', 'exclusive'],

    # Display settings
    'max_reviews_shown': 5,
    'badge_style': 'compact',  # 'compact' | 'detailed' | 'cards'
    'show_google_logo': True,

    # Dynamic dynamic content (admin editable)
    'badge_title': 'Google Reviews',
    'badge_subtitle': 'Verified client reviews from Google',
    'cta_button_text': 'Review on Google',
    'nudge_title': 'Help {{agent_name}} grow!',
    'nudge_message': 'Your review matters! Would you also leave a quick 5-star review on Google?',
    'nudge_yes_text': 'Yes, Review on Google',
    'nudge_skip_text': 'Maybe Later',
    'nudge_delay_ms': 1200,

    # Dashboard dynamic labels
    'dashboard_section_title': 'Google Reviews & Rating',
    'dashboard_section_desc': 'Showcase your Google rating & top reviews on your public profile and invite clients to review you on Google.',
    'dashboard_url_placeholder': 'https://g.page/r/.../review or your Google Place review link',
}


def _as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ('1', 'true', 'yes', 'on'):
        return True
    if text in ('0', 'false', 'no', 'off', ''):
        return False
    return default


def _as_int(value, default, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def sanitize_google_review_config(raw):
    """Sanitize and validate system-level Google Review settings."""
    data = raw if isinstance(raw, dict) else {}

    raw_eligible = data.get('eligible_plans')
    if isinstance(raw_eligible, list):
        eligible = [
            p for p in raw_eligible
            if isinstance(p, str) and normalize_plan_slug(p) in PLAN_SLUGS
        ]
    else:
        eligible = list(DEFAULT_GOOGLE_REVIEW_SYSTEM['eligible_plans'])

    max_reviews = _as_int(data.get('max_reviews_shown'), 5, minimum=1, maximum=10)
    badge_style = str(data.get('badge_style', 'compact')).strip().lower()
    if badge_style not in ('compact', 'detailed', 'cards'):
        badge_style = 'compact'

    return {
        'enabled': _as_bool(data.get('enabled'), DEFAULT_GOOGLE_REVIEW_SYSTEM['enabled']),
        'eligible_plans': eligible,
        'max_reviews_shown': max_reviews,
        'badge_style': badge_style,
        'show_google_logo': _as_bool(data.get('show_google_logo'), True),
        'badge_title': str(data.get('badge_title') or DEFAULT_GOOGLE_REVIEW_SYSTEM['badge_title']).strip(),
        'badge_subtitle': str(data.get('badge_subtitle') or DEFAULT_GOOGLE_REVIEW_SYSTEM['badge_subtitle']).strip(),
        'cta_button_text': str(data.get('cta_button_text') or DEFAULT_GOOGLE_REVIEW_SYSTEM['cta_button_text']).strip(),
        'nudge_title': str(data.get('nudge_title') or DEFAULT_GOOGLE_REVIEW_SYSTEM['nudge_title']).strip(),
        'nudge_message': str(data.get('nudge_message') or DEFAULT_GOOGLE_REVIEW_SYSTEM['nudge_message']).strip(),
        'nudge_yes_text': str(data.get('nudge_yes_text') or DEFAULT_GOOGLE_REVIEW_SYSTEM['nudge_yes_text']).strip(),
        'nudge_skip_text': str(data.get('nudge_skip_text') or DEFAULT_GOOGLE_REVIEW_SYSTEM['nudge_skip_text']).strip(),
        'nudge_delay_ms': _as_int(data.get('nudge_delay_ms'), 1200, minimum=300, maximum=10000),
        'dashboard_section_title': str(data.get('dashboard_section_title') or DEFAULT_GOOGLE_REVIEW_SYSTEM['dashboard_section_title']).strip(),
        'dashboard_section_desc': str(data.get('dashboard_section_desc') or DEFAULT_GOOGLE_REVIEW_SYSTEM['dashboard_section_desc']).strip(),
        'dashboard_url_placeholder': str(data.get('dashboard_url_placeholder') or DEFAULT_GOOGLE_REVIEW_SYSTEM['dashboard_url_placeholder']).strip(),
    }


def get_google_review_system_config():
    """Retrieve global system config from SiteSetting with fallback defaults."""
    try:
        raw = SiteSetting.get_value('google_review_system_config', None)
        if raw is None:
            # First time initialization
            return dict(DEFAULT_GOOGLE_REVIEW_SYSTEM)
        return sanitize_google_review_config(raw)
    except Exception as e:
        logger.warning('Failed to load google_review_system_config: %s', e)
        return dict(DEFAULT_GOOGLE_REVIEW_SYSTEM)


def save_google_review_system_config(config_dict):
    """Save sanitized config dict into SiteSetting."""
    sanitized = sanitize_google_review_config(config_dict)
    SiteSetting.set_value('google_review_system_config', sanitized, group='google_review')
    return sanitized


def is_google_review_enabled():
    """Check master ON/OFF switch."""
    return bool(get_google_review_system_config().get('enabled', False))


def agent_can_use_google_reviews(agent):
    """
    Check if an agent has access to Google Reviews based on:
    1. Global system switch
    2. Agent's subscription plan eligibility
    """
    if not agent:
        return False

    sys_cfg = get_google_review_system_config()
    if not sys_cfg.get('enabled', False):
        return False

    plan_slug = normalize_plan_slug(getattr(agent, 'plan_type', ''))
    eligible_plans = sys_cfg.get('eligible_plans', [])
    return plan_slug in eligible_plans


def get_agent_google_review_config(agent):
    """Fetch or create the GoogleReviewConfig record for an agent."""
    if not agent or not getattr(agent, 'id', None):
        return None
    try:
        cfg, _ = GoogleReviewConfig.objects.get_or_create(agent=agent)
        return cfg
    except Exception as e:
        logger.warning('Failed to get/create GoogleReviewConfig for agent %s: %s', agent.id, e)
        return None


def get_agent_google_review_data(agent):
    """
    Build a display-ready dictionary for agent public profile.
    Returns None if:
    - Global feature is disabled
    - Agent's plan is not eligible
    - Agent disabled their Google review showcase
    - Agent has no Google review URL
    """
    if not agent_can_use_google_reviews(agent):
        return None

    cfg = get_agent_google_review_config(agent)
    if not cfg or not cfg.is_enabled or not cfg.google_review_url:
        return None

    sys_cfg = get_google_review_system_config()
    max_reviews = sys_cfg.get('max_reviews_shown', 5)

    cached_reviews = cfg.cached_reviews if isinstance(cfg.cached_reviews, list) else []
    display_reviews = []
    for r in cached_reviews[:max_reviews]:
        if isinstance(r, dict) and r.get('text'):
            try:
                r_rating = min(5, max(1, int(r.get('rating', 5))))
            except (ValueError, TypeError):
                r_rating = 5
            display_reviews.append({
                'author': str(r.get('author') or 'Google Reviewer').strip(),
                'rating': r_rating,
                'text': str(r.get('text', '')).strip(),
                'time': str(r.get('time') or '').strip(),
            })

    rating_float = float(cfg.google_rating) if cfg.google_rating is not None else 5.0

    return {
        'enabled': True,
        'google_review_url': cfg.google_review_url,
        'rating': round(rating_float, 1),
        'review_count': cfg.google_review_count or len(display_reviews),
        'place_name': cfg.google_place_name or getattr(agent, 'fullname', ''),
        'reviews': display_reviews,
        'has_reviews': len(display_reviews) > 0,
        'badge_style': sys_cfg.get('badge_style', 'compact'),
        'show_google_logo': sys_cfg.get('show_google_logo', True),
        'badge_title': sys_cfg.get('badge_title', 'Google Reviews'),
        'badge_subtitle': sys_cfg.get('badge_subtitle', 'Verified client reviews from Google'),
        'cta_button_text': sys_cfg.get('cta_button_text', 'Review on Google'),
        'clicks': cfg.google_review_clicks,
    }


def get_google_nudge_config(agent):
    """
    Returns nudge modal config for post-platform-review popup.
    Returns None if agent cannot use Google reviews or has no review URL.
    """
    if not agent_can_use_google_reviews(agent):
        return None

    cfg = get_agent_google_review_config(agent)
    if not cfg or not cfg.is_enabled or not cfg.google_review_url:
        return None

    sys_cfg = get_google_review_system_config()
    agent_name = getattr(agent, 'fullname', '') or 'your agent'

    title = sys_cfg.get('nudge_title', '').replace('{{agent_name}}', agent_name)
    message = sys_cfg.get('nudge_message', '').replace('{{agent_name}}', agent_name)

    return {
        'enabled': True,
        'google_review_url': cfg.google_review_url,
        'title': title,
        'message': message,
        'yes_text': sys_cfg.get('nudge_yes_text', 'Yes, Review on Google'),
        'skip_text': sys_cfg.get('nudge_skip_text', 'Maybe Later'),
        'delay_ms': sys_cfg.get('nudge_delay_ms', 1200),
        'agent_id': agent.id,
    }


def track_google_review_click(agent_id, source='badge'):
    """Increment click count for agent's Google review link."""
    try:
        cfg = GoogleReviewConfig.objects.filter(agent_id=agent_id).first()
        if cfg:
            cfg.google_review_clicks += 1
            cfg.save(update_fields=['google_review_clicks', 'updated_at'])
            return cfg.google_review_clicks
    except Exception as e:
        logger.warning('Failed to track Google review click for agent %s: %s', agent_id, e)
    return 0
