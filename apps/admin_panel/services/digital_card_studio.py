"""
apps/admin_panel/services/digital_card_studio.py

Service layer for managing the Personal Digital Visiting Card Studio CMS:
- Global feature toggle (syncs with agent_digital_card_enabled)
- Studio UI header, tagline, and badges configuration
- Agent permissions (customize colors, custom banners, custom logos, external action buttons)
- Global Section Visibility Policies:
    - 'allow_agent': Agent controls via studio switch (default)
    - 'always_show': Forced ON by Admin across all agent cards
    - 'always_hide': Forced OFF by Admin across all agent cards
- Visual fallbacks (default theme color, banner style, WhatsApp greeting, tagline, bio)
- "Powered by PadosiAgent" branding / watermark badge toggle
- SEO OpenGraph title & description formatting patterns
- Audit logging via AdminActivityLog
"""

import re
import json
import logging
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlsplit
from django.core.cache import cache

logger = logging.getLogger('apps.admin_panel.services.digital_card_studio')

CACHE_KEY_STUDIO_CONFIG = 'digital_card_studio_config_v1'
CACHE_TTL = 300  # 5 minutes
MAX_CARD_URL_LENGTH = 500

DEFAULT_DIGITAL_CARD_STUDIO_CONFIG: Dict[str, Any] = {
    # 1. Master & Header
    'enabled': True,
    'studio_title': 'Personal Digital Visiting Card Studio',
    'studio_subtitle': 'Customize your professional digital card! Showcase your own agency branding, custom banner, logo, colors, and direct WhatsApp / call buttons without 3rd-party marketing.',
    'studio_badge': 'Link-In-Bio Studio',
    'style_badge': 'PassKard Style',

    # 2. Agent Customization Permissions
    'allow_theme_customization': True,
    'allow_custom_banner': True,
    'allow_custom_logo': True,
    'allow_custom_button': True,
    'allow_lead_form_toggle': True,

    # 3. Platform Branding / Watermark
    'show_powered_by_badge': True,
    'powered_by_text': 'Powered by PadosiAgent',
    'powered_by_url': '/',

    # 4. Global Visual Fallbacks
    'default_theme_color': '#0B1F3A',
    'default_banner_style': 'profile',
    'default_whatsapp_msg': 'Hello {agent_name},\nI viewed your Digital Visiting Card on PadosiAgent and would like consultation regarding insurance plans.',
    'default_card_tagline': 'Certified Insurance & Risk Advisory',
    'default_card_bio': 'Dedicated to helping families and businesses secure comprehensive coverage with prompt claims support.',

    # 5. Global Section Visibility Policies ('allow_agent', 'always_show', 'always_hide')
    'policy_call': 'allow_agent',
    'policy_whatsapp': 'allow_agent',
    'policy_email': 'allow_agent',
    'policy_address': 'allow_agent',
    'policy_save_contact': 'allow_agent',
    'policy_lead_form': 'allow_agent',
    'policy_services': 'allow_agent',
    'policy_reviews': 'allow_agent',
    'policy_qr_card': 'allow_agent',

    # 6. SEO & Meta
    'meta_title_pattern': '{agent_name} | Certified Insurance Advisor | PadosiAgent',
    'meta_description_pattern': 'Official Digital Visiting Card of {agent_name}, Certified Insurance Advisor on PadosiAgent. Save contact, explore insurance specialties, and request a free consultation.',
}

VALID_POLICIES = {'allow_agent', 'always_show', 'always_hide'}
VALID_BANNER_STYLES = {
    'profile', 'gradient_navy', 'gradient_emerald',
    'gradient_indigo', 'gradient_sunset', 'gradient_purple', 'custom'
}


def clean_card_url(value: Any) -> Optional[str]:
    """
    Return a link that is safe to put in an href: '' when blank, a site-relative path
    ('/...' but not '//' or '/\\'), or an absolute http(s) URL. Returns None when invalid.
    """
    url = re.sub(r'[\x00-\x1f\x7f]', '', str(value or '')).strip()
    if not url:
        return ''
    if len(url) > MAX_CARD_URL_LENGTH:
        return None
    if url.startswith('/'):
        return None if url[1:2] in ('/', '\\') else url
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme.lower() in ('http', 'https') and parts.netloc:
        return url
    return None


def get_digital_card_studio_config(use_cache: bool = True) -> Dict[str, Any]:
    """
    Retrieve current Digital Visiting Card Studio configuration.
    Falls back gracefully to defaults if setting does not exist yet.
    """
    if use_cache:
        cached = cache.get(CACHE_KEY_STUDIO_CONFIG)
        if isinstance(cached, dict):
            return cached

    from apps.home.models import SiteSetting

    config = dict(DEFAULT_DIGITAL_CARD_STUDIO_CONFIG)
    saved_val = SiteSetting.get_value('digital_card_studio_config', None)

    if isinstance(saved_val, dict):
        config.update(saved_val)
    elif isinstance(saved_val, str):
        try:
            parsed = json.loads(saved_val)
            if isinstance(parsed, dict):
                config.update(parsed)
        except Exception:
            pass

    # Ensure synchronization with 'agent_digital_card_enabled' master flag
    raw_master = SiteSetting.get_value('agent_digital_card_enabled', None)
    if raw_master is not None:
        config['enabled'] = str(raw_master).strip().lower() in ('1', 'true', 'yes', 'on')

    # Validate theme color
    if not re.match(r'^#[A-Fa-f0-9]{6}$', str(config.get('default_theme_color', ''))):
        config['default_theme_color'] = '#0B1F3A'

    cache.set(CACHE_KEY_STUDIO_CONFIG, config, CACHE_TTL)
    return config


def save_digital_card_studio_config(updates: Dict[str, Any], request=None) -> Dict[str, Any]:
    """
    Sanitize and persist Digital Visiting Card Studio configuration.
    Also syncs 'agent_digital_card_enabled' site setting and flushes cache.
    """
    from apps.home.models import SiteSetting

    current = get_digital_card_studio_config(use_cache=False)

    # Boolean flags
    bool_keys = [
        'enabled',
        'allow_theme_customization',
        'allow_custom_banner',
        'allow_custom_logo',
        'allow_custom_button',
        'allow_lead_form_toggle',
        'show_powered_by_badge',
    ]
    for k in bool_keys:
        if k in updates:
            val = updates[k]
            if isinstance(val, bool):
                current[k] = val
            else:
                current[k] = str(val).strip().lower() in ('1', 'true', 'yes', 'on')

    # String titles and headers
    str_keys = [
        'studio_title',
        'studio_subtitle',
        'studio_badge',
        'style_badge',
        'powered_by_text',
        'powered_by_url',
        'default_whatsapp_msg',
        'default_card_tagline',
        'default_card_bio',
        'meta_title_pattern',
        'meta_description_pattern',
    ]
    for k in str_keys:
        if k in updates:
            clean_str = str(updates[k]).strip()
            if k == 'powered_by_url':
                clean_str = clean_card_url(clean_str)
                if clean_str is None:
                    raise ValueError(
                        'Powered-by link must be a site path starting with "/" or an http(s) URL '
                        f'(max {MAX_CARD_URL_LENGTH} characters).'
                    )
            if clean_str:
                current[k] = clean_str

    # Validate Theme Color
    if 'default_theme_color' in updates:
        col = str(updates['default_theme_color']).strip()
        if re.match(r'^#[A-Fa-f0-9]{6}$', col):
            current['default_theme_color'] = col

    # Validate Banner Style
    if 'default_banner_style' in updates:
        bstyle = str(updates['default_banner_style']).strip()
        if bstyle in VALID_BANNER_STYLES:
            current['default_banner_style'] = bstyle

    # Section Policies
    policy_keys = [
        'policy_call',
        'policy_whatsapp',
        'policy_email',
        'policy_address',
        'policy_save_contact',
        'policy_lead_form',
        'policy_services',
        'policy_reviews',
        'policy_qr_card',
    ]
    for k in policy_keys:
        if k in updates:
            pval = str(updates[k]).strip().lower()
            if pval in VALID_POLICIES:
                current[k] = pval

    # Persist in SiteSetting
    SiteSetting.set_value('digital_card_studio_config', current, group='content')
    SiteSetting.set_value('agent_digital_card_enabled', current['enabled'], group='general')

    # Invalidate cache
    cache.delete(CACHE_KEY_STUDIO_CONFIG)
    cache.set(CACHE_KEY_STUDIO_CONFIG, current, CACHE_TTL)

    # Activity Log
    try:
        from apps.admin_panel.models import AdminActivityLog
        AdminActivityLog.log(
            'Updated Personal Digital Visiting Card Studio configuration',
            'SiteSetting',
            request=request
        )
    except Exception as e:
        logger.warning(f"Could not record AdminActivityLog: {e}")

    return current


def resolve_effective_section_visibility(policy_key: str, agent_preferred_val: Any, studio_cfg: Optional[Dict[str, Any]] = None) -> bool:
    """
    Determines whether a specific section should be rendered on a visiting card.
    - If policy == 'always_show': Forced ON by Admin (returns True)
    - If policy == 'always_hide': Forced OFF by Admin (returns False)
    - If policy == 'allow_agent': Uses agent's preference (default)
    """
    if studio_cfg is None:
        studio_cfg = get_digital_card_studio_config()

    policy = studio_cfg.get(policy_key, 'allow_agent')
    if policy == 'always_show':
        return True
    if policy == 'always_hide':
        return False

    if agent_preferred_val is None:
        return True
    return bool(agent_preferred_val)
