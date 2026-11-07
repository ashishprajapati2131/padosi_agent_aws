"""Coming Soon / Google Review write flows used by apps/admin_panel/views/coming_soon.py.

Exceptions propagate; the views map them to their existing JSON error responses.
"""

from apps.home.models.site_setting import SiteSetting
from apps.home.models.upcoming_feature import UpcomingFeature


DEFAULT_FEATURES = [
    {
        'title': 'AI Assist',
        'description': 'Smart replies, instant quotes and AI-drafted follow-ups for every lead.',
        'icon': 'fa-solid fa-wand-magic-sparkles',
        'status_badge': 'next_up',
        'custom_badge_text': 'Next up',
        'visible_to': 'all',
        'sort_order': 1,
        'is_active': True,
    },
    {
        'title': 'Cross Sell Products',
        'description': 'Get suggested products for each client based on what they already own.',
        'icon': 'fa-solid fa-arrows-rotate',
        'status_badge': '',
        'custom_badge_text': '',
        'visible_to': 'all',
        'sort_order': 2,
        'is_active': True,
    },
    {
        'title': 'Existing Customer Servicing Tools',
        'description': 'Endorsements, nominee updates and policy service requests in one place.',
        'icon': 'fa-solid fa-headset',
        'status_badge': '',
        'custom_badge_text': '',
        'visible_to': 'all',
        'sort_order': 3,
        'is_active': True,
    },
    {
        'title': 'VAS for Existing Customers',
        'description': 'Health check-ups, teleconsultation and lifestyle benefits you can offer.',
        'icon': 'fa-solid fa-gift',
        'status_badge': '',
        'custom_badge_text': '',
        'visible_to': 'all',
        'sort_order': 4,
        'is_active': True,
    },
    {
        'title': 'Customer Retention Tools',
        'description': 'Renewal nudges, birthday wishes and win-back campaigns on autopilot.',
        'icon': 'fa-solid fa-heart-circle-check',
        'status_badge': '',
        'custom_badge_text': '',
        'visible_to': 'all',
        'sort_order': 5,
        'is_active': True,
    },
    {
        'title': 'Marketplace',
        'description': 'Buy leads, marketing creatives and growth services from trusted partners.',
        'icon': 'fa-solid fa-store',
        'status_badge': '',
        'custom_badge_text': '',
        'visible_to': 'all',
        'sort_order': 6,
        'is_active': True,
    },
]


def auto_seed_if_empty():
    """Seed initial screenshot features if table is empty."""
    try:
        if UpcomingFeature.objects.count() == 0:
            for item in DEFAULT_FEATURES:
                UpcomingFeature.objects.create(**item)
    except Exception:
        pass


def update_feature(feature, *, title, description, icon, status_badge, custom_badge_text, visible_to, sort_order, is_active):
    feature.title = title
    feature.description = description
    feature.icon = icon
    feature.status_badge = status_badge
    feature.custom_badge_text = custom_badge_text
    feature.visible_to = visible_to
    feature.sort_order = sort_order
    feature.is_active = is_active
    feature.save()
    return feature


def create_feature(*, title, description, icon, status_badge, custom_badge_text, visible_to, sort_order, is_active):
    """Create a feature; sort_order 0 means append after the current last card."""
    if sort_order == 0:
        last = UpcomingFeature.objects.order_by('-sort_order').first()
        sort_order = (last.sort_order + 1) if last else 1

    return UpcomingFeature.objects.create(
        title=title,
        description=description,
        icon=icon,
        status_badge=status_badge,
        custom_badge_text=custom_badge_text,
        visible_to=visible_to,
        sort_order=sort_order,
        is_active=is_active,
    )


def toggle_feature(feature):
    feature.is_active = not feature.is_active
    feature.save(update_fields=['is_active'])


def delete_feature(feature):
    """Delete the feature; returns its title."""
    title = feature.title
    feature.delete()
    return title


def reorder_features(order_data):
    for index, fid in enumerate(order_data, 1):
        try:
            UpcomingFeature.objects.filter(id=int(fid)).update(sort_order=index)
        except (ValueError, TypeError):
            continue


def seed_default_features():
    """Create any missing DEFAULT_FEATURES by title; returns how many were created."""
    created_count = 0
    for item in DEFAULT_FEATURES:
        _, created = UpcomingFeature.objects.get_or_create(
            title=item['title'],
            defaults=item
        )
        if created:
            created_count += 1
    return created_count


def save_coming_soon_html(plan, html_content):
    setting_key = f'coming_soon_{plan}_html'
    SiteSetting.set_value(setting_key, html_content, group='coming_soon')


def toggle_google_review_system():
    """Flip the global Google Review system flag; returns the saved config."""
    from apps.agents.services.google_review import (
        get_google_review_system_config,
        save_google_review_system_config,
    )

    cfg = get_google_review_system_config()
    cfg['enabled'] = not cfg.get('enabled', False)
    return save_google_review_system_config(cfg)
