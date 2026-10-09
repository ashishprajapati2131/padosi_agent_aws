import json
from django.core.cache import cache
from apps.home.models.site_setting import SiteSetting

def footer_settings(request):
    """
    Exposes footer settings globally, cached using Django's caching framework.
    """
    cached_data = cache.get('footer_settings_data')
    if cached_data is None:
        keys = ['contact_email', 'contact_phone', 'contact_address', 'social_links', 'site_logo', 'site_name']
        settings_qs = SiteSetting.objects.filter(key__in=keys)
        settings_dict = {s.key: s.value for s in settings_qs}

        # Decode social links (since they are json dumps)
        social_links = settings_dict.get('social_links')
        if isinstance(social_links, str) and social_links.strip().startswith(('{', '[')):
            try:
                social_links = json.loads(social_links)
            except json.JSONDecodeError:
                social_links = {}
        elif not isinstance(social_links, dict):
            social_links = {}

        # Fill defaults if missing or empty
        cached_data = {
            'contact_email': settings_dict.get('contact_email') or 'support@padosiagent.com',
            'contact_phone': settings_dict.get('contact_phone') or '+91 80000 00000',
            'contact_address': settings_dict.get('contact_address') or 'Ahmedabad - 380009 Gujarat, India',
            'social_links': {
                'facebook': social_links.get('facebook') or '',
                'twitter': social_links.get('twitter') or '',
                'instagram': social_links.get('instagram') or '',
                'linkedin': social_links.get('linkedin') or '',
            },
            'site_logo': settings_dict.get('site_logo') or '',
            'site_name': settings_dict.get('site_name') or 'PadosiAgent',
        }
        cache.set('footer_settings_data', cached_data, timeout=None)

    return {
        'footer_settings': cached_data,
        'site_name': cached_data.get('site_name'),  # for backwards compatibility in base.html
    }

def seo_context(request):
    """
    Provides SEO and Open Graph context variables across all pages.
    - If a custom LinkOgSetting exists for request.path, it takes priority!
    - Otherwise, falls back to global SiteSetting 'og_default_image' (or /static/img/logo.png).
    Admin can change both directly from the Admin Panel without code changes.
    """
    from apps.agents.services.og_urls import build_og_absolute_url, get_public_site_base
    from apps.home.models.link_og_setting import LinkOgSetting

    # 1. Base SEO defaults from SiteSetting or fallback strings
    meta_title = SiteSetting.get_value('seo_meta_title', 'PadosiAgent — Expert & Trusted Insurance Agent')
    meta_description = SiteSetting.get_value(
        'seo_meta_description',
        'Find trusted & verified insurance experts in your neighbourhood. Connect with your local PadosiAgent.'
    )

    # 2. Global Default OG Image from SiteSetting
    global_og_image = SiteSetting.get_value('og_default_image', '')
    if global_og_image:
        if not global_og_image.startswith(('http://', 'https://')):
            global_og_image = build_og_absolute_url(request, global_og_image)
    else:
        global_og_image = build_og_absolute_url(request, '/static/img/logo.png')

    # 3. Path-specific OG / Meta override
    link_meta = None
    try:
        link_meta = LinkOgSetting.get_for_path(request.path)
    except Exception:
        link_meta = None

    final_og_image = global_og_image
    has_custom_link_og = False
    if link_meta and link_meta.get('image'):
        has_custom_link_og = True
        custom_img = link_meta['image']
        if not custom_img.startswith(('http://', 'https://')):
            final_og_image = build_og_absolute_url(request, custom_img)
        else:
            final_og_image = custom_img

        if link_meta.get('title'):
            meta_title = link_meta['title']
        if link_meta.get('description'):
            meta_description = link_meta['description']

    return {
        'default_canonical_url': build_og_absolute_url(request, request.path),
        'default_meta_title': meta_title,
        'default_meta_description': meta_description,
        'default_og_image': final_og_image,
        'has_custom_link_og': has_custom_link_og,
        'public_site_base': get_public_site_base(request),
        'site_banner': get_banner_config(request),
        'site_popup': get_exit_popup_config(request),
    }


def get_banner_config(request):
    """Fetches live top announcement banner configuration (cached 5 min)."""
    cached = cache.get('site_announcement_banner_data')
    if cached is None:
        val = SiteSetting.get_value('site_announcement_banner', None)
        if isinstance(val, str) and val.strip().startswith(('{', '[')):
            try:
                cached = json.loads(val)
            except Exception:
                cached = None
        elif isinstance(val, dict):
            cached = val
        else:
            cached = {
                'is_active': False,
                'message': '🎉 Special Offer: Connect with Verified Insurance Agents in Your Padosi!',
                'btn_text': 'Find Agents',
                'btn_url': '/find-agents/',
                'theme': 'emerald',
                'bg_color': '#059669',
                'text_color': '#ffffff',
                'is_dismissible': True,
                'target_page': 'all',
            }
        cache.set('site_announcement_banner_data', cached, timeout=300)

    if not cached or not cached.get('is_active'):
        return None

    target = cached.get('target_page', 'all')
    path = request.path
    if target == 'home_only' and path != '/':
        return None
    if target == 'agents_only' and not ('/find-agents/' in path or '/agent/' in path):
        return None

    return cached


def get_exit_popup_config(request):
    """Fetches live exit-intent lead popup configuration (cached 5 min)."""
    cached = cache.get('site_exit_popup_data')
    if cached is None:
        val = SiteSetting.get_value('site_exit_popup', None)
        if isinstance(val, str) and val.strip().startswith(('{', '[')):
            try:
                cached = json.loads(val)
            except Exception:
                cached = None
        elif isinstance(val, dict):
            cached = val
        else:
            cached = {
                'is_active': False,
                'popup_type': 'lead_form',
                'eyebrow': 'WAIT! BEFORE YOU GO',
                'title': 'Need Free Guidance from a Local Insurance Advisor?',
                'description': 'Tell us your pincode & insurance need. A verified licensed advisor will connect with you within 15 minutes. 100% free consultation!',
                'btn_text': 'Request Free Callback',
                'btn_url': '/find-agents/',
                'timer_seconds': 15,
                'dismiss_days': 3,
                'target_page': 'all',
            }
        cache.set('site_exit_popup_data', cached, timeout=300)

    if not cached or not cached.get('is_active'):
        return None

    target = cached.get('target_page', 'all')
    path = request.path
    if target == 'home_only' and path != '/':
        return None
    if target == 'agents_only' and not ('/find-agents/' in path or '/agent/' in path):
        return None

    return cached


def calculator_nav(request):
    """Show Calculators in header/footer only when at least one is live."""
    from apps.home.models.calculator import Calculator, NAV_CACHE_KEY

    cached = cache.get(NAV_CACHE_KEY)
    if cached is None:
        try:
            cached = Calculator.objects.filter(is_active=True, engine_ready=True).exists()
        except Exception:
            cached = False
        cache.set(NAV_CACHE_KEY, cached, timeout=None)
    return {'show_calculators_nav': bool(cached)}

