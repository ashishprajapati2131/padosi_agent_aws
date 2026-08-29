"""
QR service + review-growth settings.

Admin-managed SiteSetting JSON. Unlocks are additive only — they never
remove plan checkbox entitlements.
"""
import logging

from apps.agents.services.feature_unlock import (
    FEATURE_ATTR_MAP,
    PLAN_SLUGS,
    normalize_plan_slug,
)
from apps.home.models import SiteSetting

logger = logging.getLogger(__name__)

QR_TYPES = ('profile', 'card', 'reviews')

QR_TYPE_LABELS = {
    'profile': 'Profile',
    'card': 'Agent Card',
    'reviews': 'Reviews & Rating',
}

DEFAULT_QR_CONFIG = {
    'enabled': True,
    'allow_download': True,
}

DEFAULT_UNLOCK_FEATURES = (
    'sales_insights',
    'view_reviews',
    'public_profile',
    'rank_boost_tips',
)

DEFAULT_REVIEW_GROWTH = {
    'enabled': True,
    'popup_enabled': True,
    'popup_delay_ms': 2500,
    'min_reviews': 3,
    'eligible_plans': ['starter'],
    'unlock_feature_slugs': list(DEFAULT_UNLOCK_FEATURES),
    'upgrade_plan': 'professional',
    'upgrade_title': 'Unlock full visibility',
    'upgrade_message': (
        'You have collected enough reviews to unlock more dashboard features. '
        'Upgrade to Professional for AIO, GEO, SEO and Priority Ranking — '
        'and open every remaining locked section.'
    ),
    'review_scroll_delay_ms': 3000,
    'visibility_section_enabled': True,
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


def sanitize_qr_config(raw):
    data = raw if isinstance(raw, dict) else {}
    return {
        'enabled': _as_bool(data.get('enabled'), True),
        'allow_download': _as_bool(data.get('allow_download'), True),
    }


def sanitize_review_growth_config(raw):
    data = raw if isinstance(raw, dict) else {}
    eligible = [
        p for p in (data.get('eligible_plans') or DEFAULT_REVIEW_GROWTH['eligible_plans'])
        if p in PLAN_SLUGS
    ]
    if not eligible:
        eligible = list(DEFAULT_REVIEW_GROWTH['eligible_plans'])

    unlock = []
    for feat in data.get('unlock_feature_slugs') or DEFAULT_UNLOCK_FEATURES:
        feat = str(feat or '').strip()
        if feat in FEATURE_ATTR_MAP and feat not in unlock:
            unlock.append(feat)

    upgrade_plan = normalize_plan_slug(data.get('upgrade_plan') or 'professional')
    if upgrade_plan not in PLAN_SLUGS:
        upgrade_plan = 'professional'

    title = str(data.get('upgrade_title') or DEFAULT_REVIEW_GROWTH['upgrade_title']).strip()
    message = str(data.get('upgrade_message') or DEFAULT_REVIEW_GROWTH['upgrade_message']).strip()
    if not title:
        title = DEFAULT_REVIEW_GROWTH['upgrade_title']
    if not message:
        message = DEFAULT_REVIEW_GROWTH['upgrade_message']

    return {
        'enabled': _as_bool(data.get('enabled'), True),
        'popup_enabled': _as_bool(data.get('popup_enabled'), True),
        'popup_delay_ms': _as_int(data.get('popup_delay_ms'), 2500, 1500, 5000),
        'min_reviews': _as_int(data.get('min_reviews'), 3, 1, 50),
        'eligible_plans': eligible,
        'unlock_feature_slugs': unlock or list(DEFAULT_UNLOCK_FEATURES),
        'upgrade_plan': upgrade_plan,
        'upgrade_title': title[:160],
        'upgrade_message': message[:800],
        'review_scroll_delay_ms': _as_int(
            data.get('review_scroll_delay_ms'), 3000, 2000, 5000
        ),
        'visibility_section_enabled': _as_bool(
            data.get('visibility_section_enabled'), True
        ),
    }


def get_qr_config():
    try:
        return sanitize_qr_config(SiteSetting.get_value('qr_service_config', DEFAULT_QR_CONFIG))
    except Exception:
        logger.exception('Failed to load qr_service_config')
        return dict(DEFAULT_QR_CONFIG)


def get_review_growth_config():
    try:
        return sanitize_review_growth_config(
            SiteSetting.get_value('review_growth_config', DEFAULT_REVIEW_GROWTH)
        )
    except Exception:
        logger.exception('Failed to load review_growth_config')
        return dict(DEFAULT_REVIEW_GROWTH)


def is_qr_enabled():
    return bool(get_qr_config().get('enabled'))


def agent_review_count(agent):
    try:
        return int(getattr(agent, 'review_count', 0) or 0)
    except (TypeError, ValueError):
        return 0


def _plan_slug(agent):
    return normalize_plan_slug(getattr(agent, 'plan_type', '') or '')


def should_show_popup(agent):
    cfg = get_review_growth_config()
    if not cfg.get('enabled') or not cfg.get('popup_enabled'):
        return False
    return agent_review_count(agent) < cfg['min_reviews']


def should_show_upgrade_cta(agent):
    cfg = get_review_growth_config()
    if not cfg.get('enabled'):
        return False
    slug = _plan_slug(agent)
    if slug not in cfg.get('eligible_plans', []):
        return False
    if slug == cfg.get('upgrade_plan'):
        return False
    return agent_review_count(agent) >= cfg['min_reviews']


def extra_unlock_attrs(agent):
    """show_* attribute names to ADD when review threshold is met."""
    cfg = get_review_growth_config()
    if not cfg.get('enabled') or agent is None:
        return set()
    slug = _plan_slug(agent)
    if slug not in cfg.get('eligible_plans', []):
        return set()
    if agent_review_count(agent) < cfg['min_reviews']:
        return set()
    attrs = set()
    for feat in cfg.get('unlock_feature_slugs') or []:
        attrs.update(FEATURE_ATTR_MAP.get(feat, []))
    return attrs


def build_review_growth_hints(agent):
    """Remaining-condition fragments for features this config would unlock."""
    cfg = get_review_growth_config()
    if not cfg.get('enabled') or agent is None:
        return {}
    slug = _plan_slug(agent)
    if slug not in cfg.get('eligible_plans', []):
        return {}
    count = agent_review_count(agent)
    needed = cfg['min_reviews']
    if count >= needed:
        return {}
    fragment = f'{needed} reviews ({count}/{needed})'
    hints = {}
    for feat in cfg.get('unlock_feature_slugs') or []:
        if feat not in hints:
            hints[feat] = fragment
        for attr in FEATURE_ATTR_MAP.get(feat, []):
            if attr not in hints:
                hints[attr] = fragment
    return hints
