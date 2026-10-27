"""
apps/admin_panel/services/feature_flags.py

Enterprise-grade Feature Flag Management Service for PadosiAgent.
Handles:
- Centralized registry of system & custom feature flags
- Synchronized reading & writing to individual SiteSetting keys for 100% backward compatibility
- Instant AJAX ON/OFF toggling with cache flushing
- Target section URL resolution for 1-click admin redirection
- Strict security validation, CSRF verification, and AdminActivityLog audit tracking
"""

import re
import json
import logging
from typing import Dict, List, Optional, Any
from django.utils import timezone
from django.core.cache import cache

from apps.home.models.site_setting import SiteSetting
from apps.admin_panel.models.admin_activity_log import AdminActivityLog

logger = logging.getLogger(__name__)

FEATURE_FLAGS_REGISTRY_KEY = 'admin_feature_flags_registry'
FEATURE_FLAGS_CACHE_KEY = 'feature_flags_all_v1'

# Built-in System Feature Flags pre-configured with descriptions, categories, icons, and redirect routes
DEFAULT_SYSTEM_FLAGS: List[Dict[str, Any]] = [
    {
        'key': 'wholesale_marketplace_enabled',
        'name': 'B2B Wholesale Marketplace',
        'category': 'Core Platform',
        'description': 'Master switch for wholesale distributor marketplace, B2B product catalogs, and ordering workflows. When disabled, wholesale portals show offline maintenance notice.',
        'redirect_url': '/wholesale/admin/dashboard/',
        'default': False,
        'icon': 'fa-solid fa-truck-ramp-box',
        'is_system': True,
    },
    {
        'key': 'agent_digital_card_enabled',
        'name': 'Agent Digital Visiting Card',
        'category': 'Growth & Marketing',
        'description': 'Allows insurance agents to generate, customize, and share live digital visiting cards with QR codes, WhatsApp direct links, and client lead forms.',
        'redirect_url': '/admin/agents/?status=active',
        'default': True,
        'icon': 'fa-solid fa-id-card',
        'is_system': True,
    },
    {
        'key': 'wa_agent_bot_enabled',
        'name': 'WhatsApp Agent Bot Automation',
        'category': 'Automation & AI',
        'description': 'Governs the automated WhatsApp assistant and notification dispatch for agents, onboarding reminders, and real-time lead delivery.',
        'redirect_url': '/admin/whatsapp/',
        'default': True,
        'icon': 'fa-brands fa-whatsapp',
        'is_system': True,
    },
    {
        'key': 'feature_flag_pincode_heatmap',
        'name': 'Pincode Heatmap (BI & Demographics)',
        'category': 'BI & Analytics',
        'description': 'Business intelligence geographic heatmap showing agent concentration, demand coverage, and underserved pincodes across India.',
        'redirect_url': '/admin/pincode-heatmap/',
        'default': True,
        'icon': 'fa-solid fa-fire-flame-curved',
        'is_system': True,
    },
    {
        'key': 'profile_banner_enabled',
        'name': 'Agent Profile Banner Studio',
        'category': 'Growth & Marketing',
        'description': 'Enables custom branded profile headers, preset banners, and promotional cover graphics on public agent profile pages.',
        'redirect_url': '/admin/profile-banners/',
        'default': True,
        'icon': 'fa-solid fa-image',
        'is_system': True,
    },
    {
        'key': 'profile_banner_allow_custom_upload',
        'name': 'Agent Custom Banner File Uploads',
        'category': 'Growth & Marketing',
        'description': 'Permits agents to upload their own customized graphic banners rather than choosing exclusively from admin-curated presets.',
        'redirect_url': '/admin/profile-banners/',
        'default': True,
        'icon': 'fa-solid fa-cloud-arrow-up',
        'is_system': True,
    },
    {
        'key': 'site_announcement_banner_enabled',
        'name': 'Global Announcement Header Banner',
        'category': 'Growth & Marketing',
        'description': 'Displays a top marquee announcement ribbon across public website pages with custom call-to-action buttons and notifications.',
        'redirect_url': '/admin/settings/banner-popup/',
        'default': False,
        'icon': 'fa-solid fa-bullhorn',
        'is_system': True,
    },
    {
        'key': 'site_exit_popup_enabled',
        'name': 'Exit Intent Lead Capture Popup',
        'category': 'Growth & Marketing',
        'description': 'Triggers a high-converting lead generation modal when desktop users move their cursor towards leaving the website.',
        'redirect_url': '/admin/settings/banner-popup/',
        'default': False,
        'icon': 'fa-solid fa-window-restore',
        'is_system': True,
    },
    {
        'key': 'subscription_expiry_enforced',
        'name': 'Subscription Expiry & Gate Enforcement',
        'category': 'Security & Compliance',
        'description': 'Automatically revokes public listing and premium portal perks once an agent\'s 365-day subscription or trial period lapses.',
        'redirect_url': '/admin/settings/security/',
        'default': True,
        'icon': 'fa-solid fa-calendar-xmark',
        'is_system': True,
    },
    {
        'key': 'event_referral_test_mode',
        'name': 'Referral Championship Sandbox / Test Mode',
        'category': 'Growth & Marketing',
        'description': 'Enables testing mode for referral reward simulations and points calculation without altering live agent balances.',
        'redirect_url': '/admin/referrals/',
        'default': False,
        'icon': 'fa-solid fa-trophy',
        'is_system': True,
    },
    {
        'key': 'qr_service_enabled',
        'name': 'Agent QR Code Marketing Generator',
        'category': 'Growth & Marketing',
        'description': 'Dynamically generates branded SVG and PNG QR codes linking directly to agent profiles and lead capture forms.',
        'redirect_url': '/admin/qr-files/',
        'default': True,
        'icon': 'fa-solid fa-qrcode',
        'is_system': True,
    },
    {
        'key': 'fastapi_services_enabled',
        'name': 'High-Performance FastAPI Services Hub',
        'category': 'Developer & API',
        'description': 'Controls FastAPI backend endpoints for high-speed mobile client API interactions and interactive OpenAPI documentation.',
        'redirect_url': '/api/docs',
        'default': True,
        'icon': 'fa-solid fa-code',
        'is_system': True,
    },
    {
        'key': 'google_review_system_enabled',
        'name': 'Automated Google Review Collection',
        'category': 'Growth & Marketing',
        'description': 'Coordinates automated feedback and Google My Business review invitations after verified client interactions.',
        'redirect_url': '/admin/reviews/',
        'default': False,
        'icon': 'fa-brands fa-google',
        'is_system': True,
    },
    {
        'key': 'find_agent_locator_v2',
        'name': 'Enhanced Geospatial Agent Locator',
        'category': 'Core Platform',
        'description': 'Powers the interactive radius-based agent discovery tool with auto-detected coordinates and postal code fallback.',
        'redirect_url': '/admin/find-agent-locator/',
        'default': True,
        'icon': 'fa-solid fa-location-crosshairs',
        'is_system': True,
    },
]


def _parse_bool_value(val: Any, default: bool = False) -> bool:
    """Parse various string/bool/int representations into a standard boolean."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ('1', 'true', 'yes', 'on', 'enabled', 'active'):
            return True
        if s in ('0', 'false', 'no', 'off', 'disabled', 'inactive', ''):
            return False
    return default


def _read_live_status(flag_def: Dict[str, Any]) -> bool:
    """
    Read the live status of a feature flag directly from SiteSetting.
    Handles both direct keys and compound JSON configurations (e.g. banner / popup).
    """
    key = flag_def['key']
    default_val = flag_def.get('default', False)

    try:
        if key == 'site_announcement_banner_enabled':
            banner_data = SiteSetting.get_value('site_announcement_banner', {})
            if isinstance(banner_data, dict):
                return bool(banner_data.get('is_active', False))
            return default_val

        if key == 'site_exit_popup_enabled':
            popup_data = SiteSetting.get_value('site_exit_popup', {})
            if isinstance(popup_data, dict):
                return bool(popup_data.get('is_active', False))
            return default_val

        raw_val = SiteSetting.get_value(key, None)
        if raw_val is None:
            return default_val
        return _parse_bool_value(raw_val, default_val)
    except Exception as e:
        logger.warning(f"Error reading live status for feature flag '{key}': {e}")
        return default_val


def _sync_live_status_to_db(flag_def: Dict[str, Any], is_enabled: bool, category: str = 'general') -> None:
    """
    Persist the boolean state to the respective SiteSetting row
    so all existing and legacy code continues to function seamlessly.
    """
    key = flag_def['key']

    if key == 'site_announcement_banner_enabled':
        banner_data = SiteSetting.get_value('site_announcement_banner', {})
        if not isinstance(banner_data, dict):
            banner_data = {}
        banner_data['is_active'] = is_enabled
        SiteSetting.set_value('site_announcement_banner', banner_data, group='general')
        return

    if key == 'site_exit_popup_enabled':
        popup_data = SiteSetting.get_value('site_exit_popup', {})
        if not isinstance(popup_data, dict):
            popup_data = {}
        popup_data['is_active'] = is_enabled
        SiteSetting.set_value('site_exit_popup', popup_data, group='general')
        return

    # Standard direct key
    db_val = '1' if is_enabled else '0'
    SiteSetting.set_value(key, db_val, group=category or 'general')


def get_custom_registry() -> Dict[str, Dict[str, Any]]:
    """Fetch user-created custom feature flags from SiteSetting."""
    try:
        raw = SiteSetting.get_value(FEATURE_FLAGS_REGISTRY_KEY, {})
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            return json.loads(raw)
    except Exception as e:
        logger.error(f"Failed to read custom feature flags registry: {e}")
    return {}


def save_custom_registry(registry: Dict[str, Dict[str, Any]]) -> None:
    """Persist custom feature flags registry to SiteSetting and clear cache."""
    try:
        SiteSetting.set_value(FEATURE_FLAGS_REGISTRY_KEY, registry, group='feature_flags')
        cache.delete(FEATURE_FLAGS_CACHE_KEY)
    except Exception as e:
        logger.error(f"Failed to save custom feature flags registry: {e}")


def get_all_feature_flags() -> List[Dict[str, Any]]:
    """
    Returns the comprehensive list of all feature flags (System + Custom).
    Each entry includes live state, metadata, and target redirect link.
    """
    custom_registry = get_custom_registry()
    flags_list: List[Dict[str, Any]] = []

    # 1. Process System Flags
    for defn in DEFAULT_SYSTEM_FLAGS:
        flag = dict(defn)
        flag['is_enabled'] = _read_live_status(defn)
        flag['is_custom'] = False
        flags_list.append(flag)

    # 2. Process Custom Flags
    for key, c_flag in custom_registry.items():
        flag = dict(c_flag)
        flag['key'] = key
        flag['is_system'] = False
        flag['is_custom'] = True
        flag['is_enabled'] = _read_live_status(flag)
        flags_list.append(flag)

    return flags_list


def get_feature_flag(key: str) -> Optional[Dict[str, Any]]:
    """Get a single feature flag definition and live status by its key."""
    for f in get_all_feature_flags():
        if f['key'] == key:
            return f
    return None


def is_feature_enabled(key: str, default: bool = False) -> bool:
    """
    Global convenience helper to check whether a feature flag is currently active.
    Can be imported anywhere: `from apps.admin_panel.services.feature_flags import is_feature_enabled`
    """
    flag = get_feature_flag(key)
    if flag:
        return flag.get('is_enabled', default)
    # Fallback to direct SiteSetting check
    val = SiteSetting.get_value(key, None)
    if val is not None:
        return _parse_bool_value(val, default)
    return default


def set_feature_flag_status(
    key: str,
    new_state: bool,
    admin_id: Optional[int] = None,
    request: Any = None
) -> Dict[str, Any]:
    """
    Toggle or update the active status of any feature flag.
    Updates the database row, flushes cache, and logs to AdminActivityLog.
    """
    flag = get_feature_flag(key)
    if not flag:
        return {'success': False, 'message': f"Feature flag '{key}' does not exist."}

    prev_state = flag.get('is_enabled', False)
    category = flag.get('category', 'general')

    # Persist live state to DB
    _sync_live_status_to_db(flag, new_state, category=category)

    # If it's a custom flag, also record the updated state & timestamp in registry
    if flag.get('is_custom'):
        registry = get_custom_registry()
        if key in registry:
            registry[key]['default'] = new_state
            registry[key]['updated_at'] = timezone.now().isoformat()
            if admin_id:
                registry[key]['updated_by'] = admin_id
            save_custom_registry(registry)

    # Invalidate caches
    SiteSetting.flush_cache()
    cache.delete(FEATURE_FLAGS_CACHE_KEY)
    cache.delete('admin_sidebar_counts_v4')
    cache.delete('digital_card_studio_config_v2')

    status_str = "Enabled" if new_state else "Disabled"
    action_msg = f"Toggled feature flag '{flag.get('name', key)}' ({key}) to {status_str}"

    try:
        AdminActivityLog.log(
            action=action_msg,
            model_type='FeatureFlag',
            model_id=None,
            details={
                'key': key,
                'name': flag.get('name'),
                'previous_state': prev_state,
                'new_state': new_state,
                'category': category,
                'redirect_url': flag.get('redirect_url', ''),
            },
            request=request,
            admin_id=admin_id,
            severity='INFO',
        )
    except Exception as e:
        logger.error(f"Audit log failure for feature flag toggle: {e}")

    return {
        'success': True,
        'key': key,
        'name': flag.get('name', key),
        'is_enabled': new_state,
        'message': f"Feature '{flag.get('name', key)}' has been successfully {status_str.lower()}.",
        'status_text': status_str,
    }


def sanitize_key(key: str) -> str:
    """Sanitize key to lowercase alphanumeric and underscores only."""
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', key.strip().lower())
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean


def sanitize_redirect_url(url: str) -> str:
    """
    Validate and sanitize redirect URL to ensure safe internal routing.
    Rejects dangerous protocols like javascript: or data:.
    """
    if not url:
        return ''
    clean = url.strip()
    # Reject javascript: or data: schemes
    if re.match(r'^(javascript|data|vbscript):', clean, re.IGNORECASE):
        return ''
    # Relative paths starting with / are safe
    if clean.startswith('/'):
        return clean
    # Safe external http/https
    if clean.startswith(('http://', 'https://')):
        return clean
    # Default prepend slash
    return f"/{clean}"


def create_custom_feature_flag(
    key: str,
    name: str,
    category: str,
    description: str,
    redirect_url: str,
    is_enabled: bool = False,
    icon: str = 'fa-solid fa-flag',
    admin_id: Optional[int] = None,
    request: Any = None
) -> Dict[str, Any]:
    """
    Create a new custom feature flag and register it in the system.
    """
    clean_key = sanitize_key(key)
    if not clean_key:
        return {'success': False, 'message': 'Invalid flag key. Please use letters, numbers, and underscores.'}

    # Check for reserved/system key conflict
    for defn in DEFAULT_SYSTEM_FLAGS:
        if defn['key'] == clean_key:
            return {'success': False, 'message': f"The key '{clean_key}' is a protected system feature flag."}

    registry = get_custom_registry()
    if clean_key in registry:
        return {'success': False, 'message': f"A feature flag with key '{clean_key}' already exists."}

    clean_name = name.strip() or clean_key.replace('_', ' ').title()
    clean_url = sanitize_redirect_url(redirect_url)
    clean_category = category.strip() or 'Custom Features'
    clean_icon = icon.strip() if icon and icon.strip().startswith('fa-') else 'fa-solid fa-flag'

    flag_record = {
        'key': clean_key,
        'name': clean_name,
        'category': clean_category,
        'description': description.strip(),
        'redirect_url': clean_url,
        'default': is_enabled,
        'icon': clean_icon,
        'is_system': False,
        'created_at': timezone.now().isoformat(),
        'updated_at': timezone.now().isoformat(),
        'created_by': admin_id,
    }

    # Save to registry
    registry[clean_key] = flag_record
    save_custom_registry(registry)

    # Persist live initial status to SiteSetting
    _sync_live_status_to_db(flag_record, is_enabled, category=clean_category)
    SiteSetting.flush_cache()

    try:
        AdminActivityLog.log(
            action=f"Created custom feature flag: '{clean_name}' ({clean_key})",
            model_type='FeatureFlag',
            model_id=None,
            details=flag_record,
            request=request,
            admin_id=admin_id,
            severity='INFO',
        )
    except Exception as e:
        logger.error(f"Audit log failure for feature flag creation: {e}")

    return {
        'success': True,
        'key': clean_key,
        'flag': flag_record,
        'message': f"Feature flag '{clean_name}' was created successfully.",
    }


def update_feature_flag_metadata(
    key: str,
    name: str,
    category: str,
    description: str,
    redirect_url: str,
    icon: Optional[str] = None,
    admin_id: Optional[int] = None,
    request: Any = None
) -> Dict[str, Any]:
    """
    Update editable metadata (name, description, category, redirect_url, icon) of a feature flag.
    """
    clean_key = sanitize_key(key)
    registry = get_custom_registry()
    clean_url = sanitize_redirect_url(redirect_url)

    if clean_key in registry:
        # Custom flag update
        rec = registry[clean_key]
        rec['name'] = name.strip() or rec['name']
        rec['category'] = category.strip() or rec['category']
        rec['description'] = description.strip()
        rec['redirect_url'] = clean_url
        if icon:
            rec['icon'] = icon.strip()
        rec['updated_at'] = timezone.now().isoformat()
        if admin_id:
            rec['updated_by'] = admin_id
        registry[clean_key] = rec
        save_custom_registry(registry)
    else:
        # Check system flag
        sys_match = next((defn for defn in DEFAULT_SYSTEM_FLAGS if defn['key'] == clean_key), None)
        if not sys_match:
            return {'success': False, 'message': f"Feature flag '{clean_key}' was not found."}

        # Store system flag overrides in registry
        rec = dict(sys_match)
        rec['name'] = name.strip() or rec['name']
        rec['category'] = category.strip() or rec['category']
        rec['description'] = description.strip()
        rec['redirect_url'] = clean_url
        if icon:
            rec['icon'] = icon.strip()
        rec['updated_at'] = timezone.now().isoformat()
        rec['is_system'] = True
        registry[clean_key] = rec
        save_custom_registry(registry)

    SiteSetting.flush_cache()

    try:
        AdminActivityLog.log(
            action=f"Updated feature flag metadata: '{clean_key}'",
            model_type='FeatureFlag',
            model_id=None,
            details={'key': clean_key, 'name': name, 'redirect_url': clean_url},
            request=request,
            admin_id=admin_id,
            severity='INFO',
        )
    except Exception as e:
        logger.error(f"Audit log failure for feature flag update: {e}")

    return {
        'success': True,
        'key': clean_key,
        'message': f"Feature flag '{clean_key}' settings have been updated.",
    }


def delete_custom_feature_flag(
    key: str,
    admin_id: Optional[int] = None,
    request: Any = None
) -> Dict[str, Any]:
    """
    Delete a user-created custom feature flag.
    Protected system flags cannot be deleted.
    """
    clean_key = sanitize_key(key)

    # Guard against deleting system flags
    if any(defn['key'] == clean_key for defn in DEFAULT_SYSTEM_FLAGS):
        return {'success': False, 'message': 'System feature flags cannot be deleted as they are essential to platform stability.'}

    registry = get_custom_registry()
    if clean_key not in registry:
        return {'success': False, 'message': f"Custom feature flag '{clean_key}' was not found."}

    deleted_record = registry.pop(clean_key)
    save_custom_registry(registry)

    # Clean up associated SiteSetting row
    try:
        SiteSetting.objects.filter(key=clean_key).delete()
    except Exception as e:
        logger.warning(f"Failed to delete SiteSetting row for {clean_key}: {e}")

    SiteSetting.flush_cache()

    try:
        AdminActivityLog.log(
            action=f"Deleted custom feature flag: '{deleted_record.get('name', clean_key)}' ({clean_key})",
            model_type='FeatureFlag',
            model_id=None,
            details=deleted_record,
            request=request,
            admin_id=admin_id,
            severity='WARNING',
        )
    except Exception as e:
        logger.error(f"Audit log failure for feature flag deletion: {e}")

    return {
        'success': True,
        'key': clean_key,
        'message': f"Custom feature flag '{deleted_record.get('name', clean_key)}' was deleted.",
    }


def get_active_flags_count() -> int:
    """Return the total number of currently active feature flags."""
    flags = get_all_feature_flags()
    return sum(1 for f in flags if f.get('is_enabled'))
