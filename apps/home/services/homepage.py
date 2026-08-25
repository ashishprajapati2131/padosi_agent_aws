"""Assemble public homepage context from admin CMS JSON, with model/default fallbacks."""

from apps.home.models.homepage import (
    HomePageSettings, HeroTrustBadge, HeroStatistic, HeroProductTile,
    HeroSlide, DidYouKnowSlide, QuickPickItem, WhyChooseCard, HowItWorksStep,
)
from apps.home.models.site_setting import SiteSetting


DEFAULT_TRUST_BADGES = [
    {'icon': 'check-circle', 'label': 'Licensed'},
    {'icon': 'shield', 'label': 'No Spam Calls'},
    {'icon': 'trending-up', 'label': 'Zero Platform Fee'},
]

DEFAULT_STATS = [
    {'label': 'Expert Agents', 'target': 1000, 'suffix': '+', 'icon': 'users', 'is_large': True, 'is_decimal': False},
    {'label': 'Cities Covered', 'target': 50, 'suffix': '+', 'icon': 'map-pin', 'is_large': False, 'is_decimal': False},
    {'label': 'Rating', 'target': 4.8, 'suffix': '', 'icon': 'star', 'is_large': False, 'is_decimal': True},
    {'label': 'Families Covered', 'target': 1, 'suffix': 'L+', 'icon': 'heart', 'is_large': False, 'is_decimal': False},
]

DEFAULT_TILES = [
    {'label': 'Health Insurance', 'icon': 'heart', 'url': '/find-agents?ServiceType=New+Policy&InsuranceType=Health+Insurance&openFilter=1', 'tileClass': 'pa-tile-rose'},
    {'label': 'Life Insurance', 'icon': 'shield', 'url': '/find-agents?ServiceType=New+Policy&InsuranceType=Life+Insurance&openFilter=1', 'tileClass': 'pa-tile-sky'},
    {'label': 'Vehicle Insurance', 'icon': 'car', 'url': '/find-agents?ServiceType=New+Policy&InsuranceType=Motor+Insurance&openFilter=1', 'tileClass': 'pa-tile-amber'},
    {'label': 'Business Insurance', 'icon': 'building-2', 'url': '/find-agents?ServiceType=New+Policy&InsuranceType=SME+Insurance&openFilter=1', 'tileClass': 'pa-tile-violet'},
]

DEFAULT_DYK_SLIDES = [
    {'accent_class': 'accent-rose', 'bg_class': 'bg-rose-500', 'icon': 'users', 'title': '3× faster claim settlements', 'body': 'Customers served by a nearby agent report claims clearing up to 3× faster — your agent walks the file through with the insurer.'},
    {'accent_class': 'accent-emerald', 'bg_class': 'bg-emerald-500', 'icon': 'shield', 'title': 'Local agents catch policy gaps', 'body': "A neighbourhood expert knows your city's hospital network, traffic risks and weather patterns — and recommends covers a tele-caller never will."},
    {'accent_class': 'accent-sky', 'bg_class': 'bg-sky-500', 'icon': 'clock', 'title': 'Face-to-face saves hours of confusion', 'body': '70%+ of policyholders say they understood their cover only after meeting an agent in person. Jargon disappears across a table.'},
    {'accent_class': 'accent-amber', 'bg_class': 'bg-amber-500', 'icon': 'trending-up', 'title': '40% lower lapse rates', 'body': 'Customers with a dedicated nearby agent are 40% less likely to let a policy lapse — they get timely renewal nudges from a real human.'},
    {'accent_class': 'accent-violet', 'bg_class': 'bg-violet-500', 'icon': 'lightbulb', 'title': 'Zero platform fee, full licensed advice', 'body': 'Your agent earns from the insurer — not from you. Same premium, lifetime advisor in your neighbourhood.'},
    {'accent_class': 'accent-pink', 'bg_class': 'bg-pink-500', 'icon': 'heart', 'title': 'Lifetime relationship, not a ticket number', 'body': 'Your Padosi agent stays the same across renewals, claims and family additions — no fresh call-centre script each time.'},
    {'accent_class': 'accent-indigo', 'bg_class': 'bg-indigo-500', 'icon': 'building-2', 'title': 'Hospital networks matter locally', 'body': 'A local agent maps the right cashless hospitals near your home and office before you ever need one.'},
    {'accent_class': 'accent-teal', 'bg_class': 'bg-teal-500', 'icon': 'indian-rupee', 'title': 'Right cover, not the costliest cover', 'body': 'A neighbourhood advisor sizes the premium to your real life — not to a target sheet.'},
]

DEFAULT_QUICK_PICKS = [
    {'label': 'Mediclaim', 'badge_text': 'Most Bought', 'badge_bg_color': '#ffe4e6', 'badge_text_color': '#be123c', 'icon_bg_color': '#fff1f2', 'icon_color': '#f43f5e', 'icon': 'heart-pulse', 'url': '/find-agents?ServiceType=New%20Policy&InsuranceType=Health%20Insurance&InsuranceCompany=Mediclaim&openFilter=1'},
    {'label': 'Term Plan', 'badge_text': 'Pure Cover', 'badge_bg_color': '#e0f2fe', 'badge_text_color': '#0369a1', 'icon_bg_color': '#f0f9ff', 'icon_color': '#0284c7', 'icon': 'clock', 'url': '/find-agents?ServiceType=New%20Policy&InsuranceType=Life%20Insurance&InsuranceCompany=Term%20Plan&openFilter=1'},
    {'label': 'Private Car', 'badge_text': 'Renew Fast', 'badge_bg_color': '#fef3c7', 'badge_text_color': '#b45309', 'icon_bg_color': '#fffbeb', 'icon_color': '#d97706', 'icon': 'car-front', 'url': '/find-agents?ServiceType=New%20Policy&InsuranceType=Motor%20Insurance&InsuranceCompany=Private%20Car&openFilter=1'},
    {'label': 'Two Wheeler', 'badge_text': '', 'badge_bg_color': '', 'badge_text_color': '', 'icon_bg_color': '#ecfdf5', 'icon_color': '#059669', 'icon': 'bike', 'url': '/find-agents?ServiceType=New%20Policy&InsuranceType=Motor%20Insurance&InsuranceCompany=Two%20Wheeler&openFilter=1'},
    {'label': 'Critical Illness', 'badge_text': 'Lumpsum', 'badge_bg_color': '#fae8ff', 'badge_text_color': '#a21caf', 'icon_bg_color': '#fdf4ff', 'icon_color': '#c026d3', 'icon': 'alert-triangle', 'url': '/find-agents?ServiceType=New%20Policy&InsuranceType=Health%20Insurance&InsuranceCompany=Critical%20Illness&openFilter=1'},
    {'label': 'Personal Accident', 'badge_text': '', 'badge_bg_color': '', 'badge_text_color': '', 'icon_bg_color': '#fff7ed', 'icon_color': '#ea580c', 'icon': 'user-check', 'url': '/find-agents?ServiceType=New%20Policy&InsuranceType=Health%20Insurance&InsuranceCompany=Personal%20Accident&openFilter=1'},
    {'label': 'Super Top-up', 'badge_text': 'Save Big', 'badge_bg_color': '#ccfbf1', 'badge_text_color': '#0f766e', 'icon_bg_color': '#f0fdfa', 'icon_color': '#0d9488', 'icon': 'trending-up', 'url': '/find-agents?ServiceType=New%20Policy&InsuranceType=Health%20Insurance&InsuranceCompany=Super%20Top-up&openFilter=1'},
    {'label': 'ULIP Plan', 'badge_text': '', 'badge_bg_color': '', 'badge_text_color': '', 'icon_bg_color': '#f5f3ff', 'icon_color': '#7c3aed', 'icon': 'bar-chart-3', 'url': '/find-agents?ServiceType=New%20Policy&InsuranceType=Life%20Insurance&InsuranceCompany=ULIP%20Plan&openFilter=1'},
    {'label': 'Pension Plan', 'badge_text': 'Lifetime', 'badge_bg_color': '#e0e7ff', 'badge_text_color': '#4338ca', 'icon_bg_color': '#eef2ff', 'icon_color': '#4f46e5', 'icon': 'landmark', 'url': '/find-agents?ServiceType=New%20Policy&InsuranceType=Life%20Insurance&InsuranceCompany=Pension%20Plan&openFilter=1'},
    {'label': 'Saving Plan', 'badge_text': '', 'badge_bg_color': '', 'badge_text_color': '', 'icon_bg_color': '#fdf2f8', 'icon_color': '#db2777', 'icon': 'piggy-bank', 'url': '/find-agents?ServiceType=New%20Policy&InsuranceType=Life%20Insurance&InsuranceCompany=Saving%20Plan&openFilter=1'},
    {'label': 'Commercial Vehicle', 'badge_text': '', 'badge_bg_color': '', 'badge_text_color': '', 'icon_bg_color': '#fef9c3', 'icon_color': '#a16207', 'icon': 'truck', 'url': '/find-agents?ServiceType=New%20Policy&InsuranceType=Motor%20Insurance&InsuranceCompany=Commercial%20Vehicle&openFilter=1'},
    {'label': 'Fire (SME)', 'badge_text': '', 'badge_bg_color': '', 'badge_text_color': '', 'icon_bg_color': '#fef2f2', 'icon_color': '#dc2626', 'icon': 'flame', 'url': '/find-agents?ServiceType=New%20Policy&InsuranceType=SME%20Insurance&InsuranceCompany=Others&openFilter=1'},
    {'label': 'Cyber (SME)', 'badge_text': 'New', 'badge_bg_color': '#cffafe', 'badge_text_color': '#0e7490', 'icon_bg_color': '#ecfeff', 'icon_color': '#0891b2', 'icon': 'lock', 'url': '/find-agents?ServiceType=New%20Policy&InsuranceType=SME%20Insurance&InsuranceCompany=Cyber%20(SME)&openFilter=1'},
    {'label': 'Liability (SME)', 'badge_text': '', 'badge_bg_color': '', 'badge_text_color': '', 'icon_bg_color': '#f1f5f9', 'icon_color': '#475569', 'icon': 'scale', 'url': '/find-agents?ServiceType=New%20Policy&InsuranceType=SME%20Insurance&InsuranceCompany=Liability%20(SME)&openFilter=1'},
]

DEFAULT_WHY_CARDS = [
    {'stat_text': '0', 'caption': 'Spam Calls', 'icon': 'shield-check', 'title': 'Privacy-first by design', 'body': 'Only YOU can contact an agent. Agents can never call you first — your number is never sold or shared.'},
    {'stat_text': '₹0', 'caption': 'Platform Fee', 'icon': 'indian-rupee', 'title': '100% free for buyers', 'body': 'No charges, no hidden costs. Your premium stays the same — the agent earns from the insurer, never from you.'},
    {'stat_text': '100%', 'caption': 'Licensed Agents', 'icon': 'badge-check', 'title': 'Verified, licensed experts only', 'body': 'Every agent is a licensed insurance professional, vetted before listing. No call-centre scripts, ever.'},
    {'stat_text': '1,000+', 'caption': 'Padosi Agents', 'icon': 'map-pin', 'title': 'A neighbour in every PIN code', 'body': 'Discover trusted advisors within your locality who understand local hospitals, traffic and risks.'},
    {'stat_text': '1L+', 'caption': 'Families Covered', 'icon': 'users', 'title': 'A network you can rely on', 'body': 'Lakhs of Indian families have already found their PadosiAgent for buying, renewing and claims.'},
    {'stat_text': '5.0★', 'caption': 'Average Rating', 'icon': 'star', 'title': 'Loved by buyers across India', 'body': 'Real reviews from real customers — no incentivised ratings, no fake testimonials.'},
]

DEFAULT_WORKS_STEPS = [
    {'icon': 'search', 'accent_class': 'accent-primary', 'badge_number': '1', 'title': 'Search', 'description': 'Find verified agents', 'tooltip': 'Find verified insurance experts by area or service.'},
    {'icon': 'git-compare', 'accent_class': 'accent-secondary', 'badge_number': '2', 'title': 'Compare', 'description': 'Review ratings', 'tooltip': 'Review ratings and profiles to find your perfect match.'},
    {'icon': 'message-square', 'accent_class': 'accent-accent', 'badge_number': '3', 'title': 'Connect', 'description': 'Call or WhatsApp', 'tooltip': 'Get in touch via Call or WhatsApp instantly.'},
    {'icon': 'hand-heart', 'accent_class': 'accent-violet', 'badge_number': '4', 'title': 'Assist Me', 'description': 'Personalized service', 'tooltip': 'Get professional support for policies, claims, and more.'},
]

SLIDE_GRADIENTS = [
    'linear-gradient(135deg, hsla(var(--pa-primary-h), var(--pa-primary-s), var(--pa-primary-l), 0.25), hsla(var(--pa-primary-h), var(--pa-primary-s), var(--pa-primary-l), 0.1), hsla(var(--pa-primary-h), var(--pa-primary-s), var(--pa-primary-l), 0.05))',
    'linear-gradient(135deg, hsla(var(--pa-secondary-h), var(--pa-secondary-s), var(--pa-secondary-l), 0.25), hsla(var(--pa-secondary-h), var(--pa-secondary-s), var(--pa-secondary-l), 0.1), hsla(var(--pa-secondary-h), var(--pa-secondary-s), var(--pa-secondary-l), 0.05))',
    'linear-gradient(135deg, hsla(0, 72%, 51%, 0.25), hsla(0, 72%, 51%, 0.1), hsla(0, 72%, 51%, 0.05))',
    'linear-gradient(135deg, hsla(38, 92%, 50%, 0.25), hsla(38, 92%, 50%, 0.1), hsla(38, 92%, 50%, 0.05))',
    'linear-gradient(135deg, hsla(173, 80%, 36%, 0.25), hsla(173, 80%, 36%, 0.1), hsla(173, 80%, 36%, 0.05))',
    'linear-gradient(135deg, hsla(160, 84%, 39%, 0.25), hsla(160, 84%, 39%, 0.1), hsla(160, 84%, 39%, 0.05))',
    'linear-gradient(135deg, hsla(262, 83%, 58%, 0.25), hsla(262, 83%, 58%, 0.1), hsla(262, 83%, 58%, 0.05))',
]
SLIDE_ICON_SHADOWS = [
    '0 10px 15px -3px hsla(var(--pa-primary-h), var(--pa-primary-s), var(--pa-primary-l), 0.2), 0 4px 6px -4px hsla(var(--pa-primary-h), var(--pa-primary-s), var(--pa-primary-l), 0.2)',
    '0 10px 15px -3px hsla(var(--pa-secondary-h), var(--pa-secondary-s), var(--pa-secondary-l), 0.2), 0 4px 6px -4px hsla(var(--pa-secondary-h), var(--pa-secondary-s), var(--pa-secondary-l), 0.2)',
    '0 10px 15px -3px hsla(0, 72%, 51%, 0.2), 0 4px 6px -4px hsla(0, 72%, 51%, 0.2)',
    '0 10px 15px -3px hsla(38, 92%, 50%, 0.2), 0 4px 6px -4px hsla(38, 92%, 50%, 0.2)',
    '0 10px 15px -3px hsla(173, 80%, 36%, 0.2), 0 4px 6px -4px hsla(173, 80%, 36%, 0.2)',
    '0 10px 15px -3px hsla(160, 84%, 39%, 0.2), 0 4px 6px -4px hsla(160, 84%, 39%, 0.2)',
    '0 10px 15px -3px hsla(262, 83%, 58%, 0.2), 0 4px 6px -4px hsla(262, 83%, 58%, 0.2)',
]
CARD_ACCENTS = [
    {'color': '#0065ff', 'class': 'pb-accent-blue'},
    {'color': '#10b981', 'class': 'pb-accent-green'},
    {'color': '#0ea5e9', 'class': 'pb-accent-sky'},
    {'color': '#d97706', 'class': 'pb-accent-orange'},
    {'color': '#7c3aed', 'class': 'pb-accent-purple'},
    {'color': '#14b8a6', 'class': 'pb-accent-teal'},
]


def _as_list(value):
    return value if isinstance(value, list) else []


def _is_visible(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _flag(value):
    return str(value).strip().lower() in ('true', '1', 'yes', 'on')


def _attr(obj, *names, default=''):
    for name in names:
        if isinstance(obj, dict):
            if name in obj and obj[name] not in (None, ''):
                return obj[name]
        else:
            val = getattr(obj, name, None)
            if val not in (None, ''):
                return val
    return default


def _first_filled(*values):
    for value in values:
        if isinstance(value, list) and value:
            return value
    return []


def _map_badges(items):
    mapped = []
    for item in items:
        label = _attr(item, 'label')
        if not label:
            continue
        mapped.append({'icon': _attr(item, 'icon', default='check-circle'), 'label': label})
    return mapped


def _map_stats(items):
    mapped = []
    for item in items:
        label = _attr(item, 'label')
        if not label:
            continue
        try:
            target = float(_attr(item, 'target', default=0) or 0)
        except (TypeError, ValueError):
            target = 0.0
        mapped.append({
            'label': label,
            'target': target,
            'suffix': _attr(item, 'suffix'),
            'icon': _attr(item, 'icon', default='users'),
            'is_large': _flag(_attr(item, 'is_large', 'large', default=False)),
            'is_decimal': _flag(_attr(item, 'is_decimal', 'decimal', default=False)),
        })
    return mapped


def _map_tiles(items):
    mapped = []
    for item in items:
        label = _attr(item, 'label')
        if not label:
            continue
        mapped.append({
            'label': label,
            'icon': _attr(item, 'icon', default='heart'),
            'url': _attr(item, 'url', default='#'),
            'tileClass': _attr(item, 'tileClass', 'css_class', default='pa-tile-rose'),
        })
    return mapped


def _map_hero_slides(items):
    mapped = []
    for item in items:
        hero_text = _attr(item, 'hero', 'hero_text')
        if not hero_text:
            continue
        mapped.append({
            'icon': _attr(item, 'icon', default='users'),
            'hero': hero_text,
            'hero_text': hero_text,
            'tag': _attr(item, 'tag'),
            'body': _attr(item, 'body'),
            'isChart': _flag(_attr(item, 'isChart', 'is_chart', default=False)),
            'is_chart': _flag(_attr(item, 'isChart', 'is_chart', default=False)),
        })
    return mapped


def _map_dyk(items):
    mapped = []
    for item in items:
        title = _attr(item, 'title')
        if not title:
            continue
        mapped.append({
            'accent_class': _attr(item, 'accent_class', 'accent', default='accent-rose'),
            'bg_class': _attr(item, 'bg_class', 'bg', default='bg-rose-500'),
            'icon': _attr(item, 'icon', default='lightbulb'),
            'title': title,
            'body': _attr(item, 'body'),
        })
    return mapped


def _map_quick_picks(items):
    mapped = []
    for item in items:
        label = _attr(item, 'label')
        if not label:
            continue
        url = _attr(item, 'url', default='#') or '#'
        if 'Fire' in url and 'SME' in url:
            url = (
                url.replace('InsuranceCompany=Fire%20(SME)', 'InsuranceCompany=Others')
                .replace('InsuranceCompany=Fire+(SME)', 'InsuranceCompany=Others')
                .replace('InsuranceCompany=Fire (SME)', 'InsuranceCompany=Others')
            )
        mapped.append({
            'label': label,
            'badge_text': _attr(item, 'badge_text', 'badge'),
            'badge_bg_color': _attr(item, 'badge_bg_color', 'badge_bg', default='#ffe4e6'),
            'badge_text_color': _attr(item, 'badge_text_color', 'badge_color', default='#be123c'),
            'icon_bg_color': _attr(item, 'icon_bg_color', 'icon_bg', default='#fff1f2'),
            'icon_color': _attr(item, 'icon_color', default='#f43f5e'),
            'icon': _attr(item, 'icon', default='heart'),
            'url': url,
        })
    return mapped


def _map_why_cards(items):
    mapped = []
    for item in items:
        title = _attr(item, 'title')
        if not title:
            continue
        mapped.append({
            'stat_text': _attr(item, 'stat_text', 'stat'),
            'caption': _attr(item, 'caption'),
            'icon': _attr(item, 'icon', default='shield-check'),
            'title': title,
            'body': _attr(item, 'body'),
        })
    return mapped


def _map_works_steps(items):
    mapped = []
    for item in items:
        title = _attr(item, 'title')
        if not title:
            continue
        mapped.append({
            'badge_number': _attr(item, 'badge_number', 'badge'),
            'icon': _attr(item, 'icon', default='search'),
            'accent_class': _attr(item, 'accent_class', 'accent', default='accent-primary'),
            'title': title,
            'description': _attr(item, 'description', 'desc'),
            'tooltip': _attr(item, 'tooltip'),
        })
    return mapped


def _zip_with_index(items, extra_fn=None):
    zipped = []
    for idx, item in enumerate(items):
        row = {'fact': item, 'index': idx}
        if extra_fn:
            row.update(extra_fn(idx, item))
        zipped.append(row)
    return zipped


def _overlay_settings(settings, hero, content):
    hero = hero if isinstance(hero, dict) else {}
    content = content if isinstance(content, dict) else {}
    dyk = content.get('dyk') or {}
    quickpicks = content.get('quickpicks') or {}
    why = content.get('why_choose') or {}
    works = content.get('works') or {}
    testimonials = content.get('testimonials') or {}

    if 'visible' in dyk:
        settings.show_dyk = _is_visible(dyk.get('visible'))
    if 'visible' in quickpicks:
        settings.show_quickpicks = _is_visible(quickpicks.get('visible'))
    if 'visible' in why:
        settings.show_why_choose = _is_visible(why.get('visible'))
    if 'visible' in works:
        settings.show_how_it_works = _is_visible(works.get('visible'))
    if 'visible' in testimonials:
        settings.show_testimonials = _is_visible(testimonials.get('visible'))

    field_map = [
        (dyk, 'label', 'dyk_label'),
        (dyk, 'title', 'dyk_title'),
        (quickpicks, 'label', 'quickpicks_label'),
        (quickpicks, 'title', 'quickpicks_title'),
        (quickpicks, 'view_all_text', 'quickpicks_view_all_text'),
        (quickpicks, 'view_all_url', 'quickpicks_view_all_url'),
        (why, 'label', 'why_choose_label'),
        (why, 'title', 'why_choose_title'),
        (why, 'description', 'why_choose_description'),
        (why, 'button_text', 'why_choose_button_text'),
        (why, 'button_url', 'why_choose_button_url'),
        (works, 'label', 'works_label'),
        (works, 'title', 'works_title'),
        (works, 'subtitle', 'works_subtitle'),
        (works, 'button_text', 'works_button_text'),
        (works, 'button_url', 'works_button_url'),
        (testimonials, 'label', 'testimonials_label'),
        (testimonials, 'title', 'testimonials_title'),
        (testimonials, 'subtitle', 'testimonials_subtitle'),
        (hero, 'heading', 'hero_heading'),
        (hero, 'cta_claim_text', 'hero_cta_claim_text'),
        (hero, 'cta_claim_url', 'hero_cta_claim_url'),
        (hero, 'cta_review_text', 'hero_cta_review_text'),
        (hero, 'cta_review_url', 'hero_cta_review_url'),
        (hero, 'claims_card_label', 'hero_claims_card_label'),
        (hero, 'claims_card_heading', 'hero_claims_card_heading'),
        (hero, 'claims_card_text', 'hero_claims_card_text'),
    ]
    for source, src_key, dest in field_map:
        value = source.get(src_key) if isinstance(source, dict) else None
        if value not in (None, ''):
            setattr(settings, dest, value)
    return settings


def map_custom_testimonials(custom_list):
    reviews = []
    for item in _as_list(custom_list):
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or 'User').strip() or 'User'
        service = str(item.get('service') or 'Verified Client').strip()
        comment = str(item.get('comment') or '').strip()
        try:
            rating = float(item.get('rating') or 5)
        except (TypeError, ValueError):
            rating = 5.0
        image = item.get('image') or (
            f"https://ui-avatars.com/api/?name={name.replace(' ', '+')}&background=0d9488&color=fff&bold=true"
        )
        reviews.append({
            'name': name,
            'service': service,
            'agent_url': item.get('agent_url') or None,
            'rating': rating,
            'comment': comment,
            'image': image,
        })
    return reviews


def build_homepage_cms_context():
    settings = HomePageSettings.load()
    hero = SiteSetting.get_value('hero_section', {}) or {}
    content = SiteSetting.get_value('homepage_content', {}) or {}
    if not isinstance(hero, dict):
        hero = {}
    if not isinstance(content, dict):
        content = {}

    settings = _overlay_settings(settings, hero, content)

    trust_badges = _map_badges(_first_filled(
        hero.get('trust_badges'),
        list(HeroTrustBadge.objects.all()),
        DEFAULT_TRUST_BADGES,
    ))
    stats_data = _map_stats(_first_filled(
        hero.get('stats'),
        list(HeroStatistic.objects.all()),
        DEFAULT_STATS,
    ))
    product_tiles = _map_tiles(_first_filled(
        hero.get('tiles'),
        list(HeroProductTile.objects.all()),
        DEFAULT_TILES,
    ))
    hero_slides = _map_hero_slides(_first_filled(
        hero.get('slides'),
        list(HeroSlide.objects.all()),
    ))
    dyk_slides = _map_dyk(_first_filled(
        (content.get('dyk') or {}).get('slides'),
        list(DidYouKnowSlide.objects.all()),
        DEFAULT_DYK_SLIDES,
    ))
    quick_picks = _map_quick_picks(_first_filled(
        (content.get('quickpicks') or {}).get('items'),
        list(QuickPickItem.objects.all()),
        DEFAULT_QUICK_PICKS,
    ))
    why_cards = _map_why_cards(_first_filled(
        (content.get('why_choose') or {}).get('cards'),
        list(WhyChooseCard.objects.all()),
        DEFAULT_WHY_CARDS,
    ))
    works_steps = _map_works_steps(_first_filled(
        (content.get('works') or {}).get('steps'),
        list(HowItWorksStep.objects.all()),
        DEFAULT_WORKS_STEPS,
    ))

    why_cards_zipped = []
    for idx, card in enumerate(why_cards):
        accent = CARD_ACCENTS[idx % len(CARD_ACCENTS)]
        why_cards_zipped.append({'card': card, 'accent': accent, 'index': idx})

    facts_zipped = _zip_with_index(
        hero_slides,
        lambda idx, _item: {
            'gradient': SLIDE_GRADIENTS[idx % len(SLIDE_GRADIENTS)],
            'shadow': SLIDE_ICON_SHADOWS[idx % len(SLIDE_ICON_SHADOWS)],
        },
    )
    slides_zipped = _zip_with_index(dyk_slides)

    testimonials = content.get('testimonials') or {}
    custom_reviews = []
    if _is_visible(testimonials.get('use_custom'), default=False):
        custom_reviews = map_custom_testimonials(testimonials.get('custom_list'))

    return {
        'settings': settings,
        'hero': hero,
        'trust_badges': trust_badges,
        'stats_data': stats_data,
        'product_tiles': product_tiles,
        'quick_picks': quick_picks,
        'why_cards': why_cards,
        'why_cards_zipped': why_cards_zipped,
        'works_steps': works_steps,
        'facts_zipped': facts_zipped,
        'slides_zipped': slides_zipped,
        'custom_reviews': custom_reviews,
        'hero_heading': settings.hero_heading,
    }
