from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.home.models.site_setting import SiteSetting
from apps.home.models.upcoming_feature import UpcomingFeature
from apps.admin_panel.services import coming_soon_service

import logging

logger = logging.getLogger(__name__)


def coming_soon_index(request):
    """Admin page to manage dynamic Coming Soon features + legacy HTML content."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    table_exists = True
    try:
        coming_soon_service.auto_seed_if_empty()
        features = list(UpcomingFeature.objects.all().order_by('sort_order', 'id'))
        total_count = len(features)
        active_count = len([f for f in features if f.is_active])
        starter_count = len([f for f in features if f.visible_to in ('all', 'starter')])
        pro_count = len([f for f in features if f.visible_to in ('all', 'professional')])
    except Exception:
        features = []
        total_count = 0
        active_count = 0
        starter_count = 0
        pro_count = 0
        table_exists = False

    coming_soon_starter_html = SiteSetting.get_value('coming_soon_starter_html', '') or ''
    coming_soon_professional_html = SiteSetting.get_value('coming_soon_professional_html', '') or ''

    # Google Review Rating System Context
    from apps.agents.services.google_review import get_google_review_system_config
    from apps.home.models import GoogleReviewConfig
    from apps.agents.services.feature_unlock import PLAN_LABELS, PLAN_SLUGS

    google_review_cfg = get_google_review_system_config()

    try:
        gr_configured_agents = GoogleReviewConfig.objects.count()
        gr_enabled_agents = GoogleReviewConfig.objects.filter(is_enabled=True).count()
        from django.db.models import Sum, Avg
        clicks_sum = GoogleReviewConfig.objects.aggregate(Sum('google_review_clicks'))['google_review_clicks__sum']
        gr_total_clicks = clicks_sum or 0
        avg_res = GoogleReviewConfig.objects.filter(is_enabled=True, google_rating__isnull=False).aggregate(Avg('google_rating'))['google_rating__avg']
        gr_avg_rating = round(float(avg_res), 1) if avg_res else 0.0
    except Exception:
        gr_configured_agents = 0
        gr_enabled_agents = 0
        gr_total_clicks = 0
        gr_avg_rating = 0.0

    plan_options = [
        {'slug': slug, 'label': PLAN_LABELS.get(slug, slug.title())}
        for slug in PLAN_SLUGS
    ]

    return render(request, 'admin/coming_soon/index.html', {
        'features': features,
        'total_count': total_count,
        'active_count': active_count,
        'starter_count': starter_count,
        'pro_count': pro_count,
        'table_exists': table_exists,
        'coming_soon_starter_html': coming_soon_starter_html,
        'coming_soon_professional_html': coming_soon_professional_html,
        'google_review_config': google_review_cfg,
        'gr_configured_agents': gr_configured_agents,
        'gr_enabled_agents': gr_enabled_agents,
        'gr_total_clicks': gr_total_clicks,
        'gr_avg_rating': gr_avg_rating,
        'plan_options': plan_options,
    })


@require_POST
def save_feature(request):
    """Add or update an upcoming feature card."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    feature_id = request.POST.get('feature_id')
    title = request.POST.get('title', '').strip()
    description = request.POST.get('description', '').strip()
    icon = request.POST.get('icon', '').strip() or 'fa-solid fa-wand-magic-sparkles'
    status_badge = request.POST.get('status_badge', '').strip()
    custom_badge_text = request.POST.get('custom_badge_text', '').strip()
    visible_to = request.POST.get('visible_to', 'all').strip().lower()
    sort_order = request.POST.get('sort_order', 0)
    is_active = request.POST.get('is_active') in ('1', 'true', 'on', True)

    if not title:
        return JsonResponse({'success': False, 'message': 'Feature title is required.'}, status=400)

    if visible_to not in ('all', 'starter', 'professional'):
        visible_to = 'all'

    try:
        sort_order = int(sort_order)
    except (ValueError, TypeError):
        sort_order = 0

    try:
        if feature_id:
            feature = get_object_or_404(UpcomingFeature, id=feature_id)
            coming_soon_service.update_feature(
                feature,
                title=title,
                description=description,
                icon=icon,
                status_badge=status_badge,
                custom_badge_text=custom_badge_text,
                visible_to=visible_to,
                sort_order=sort_order,
                is_active=is_active,
            )
            action_msg = 'Feature updated successfully!'
        else:
            feature = coming_soon_service.create_feature(
                title=title,
                description=description,
                icon=icon,
                status_badge=status_badge,
                custom_badge_text=custom_badge_text,
                visible_to=visible_to,
                sort_order=sort_order,
                is_active=is_active,
            )
            action_msg = 'New feature added successfully!'

        return JsonResponse({
            'success': True,
            'message': action_msg,
            'feature': {
                'id': feature.id,
                'title': feature.title,
                'description': feature.description,
                'icon': feature.icon,
                'status_badge': feature.status_badge,
                'custom_badge_text': feature.custom_badge_text,
                'badge_label': feature.badge_label,
                'visible_to': feature.visible_to,
                'sort_order': feature.sort_order,
                'is_active': feature.is_active,
            }
        })
    except Exception:
        return JsonResponse({
            'success': False,
            'message': 'Database table has not been migrated yet. Please run "python manage.py migrate" in your terminal first.'
        }, status=400)


@require_POST
def toggle_feature_status(request, id):
    """Toggle is_active on an upcoming feature."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    try:
        feature = get_object_or_404(UpcomingFeature, id=id)
        coming_soon_service.toggle_feature(feature)

        status_str = 'active' if feature.is_active else 'hidden'
        return JsonResponse({
            'success': True,
            'is_active': feature.is_active,
            'message': f'"{feature.title}" is now {status_str}.'
        })
    except Exception:
        return JsonResponse({
            'success': False,
            'message': 'Database table has not been migrated yet. Please run "python manage.py migrate" first.'
        }, status=400)


@require_POST
def delete_feature(request, id):
    """Delete an upcoming feature."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    try:
        feature = get_object_or_404(UpcomingFeature, id=id)
        title = coming_soon_service.delete_feature(feature)

        return JsonResponse({
            'success': True,
            'message': f'"{title}" removed successfully.'
        })
    except Exception:
        return JsonResponse({
            'success': False,
            'message': 'Database table has not been migrated yet. Please run "python manage.py migrate" first.'
        }, status=400)


@require_POST
def reorder_features(request):
    """Reorder upcoming features based on an array of IDs."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    import json
    order_data = request.POST.getlist('order[]')
    if not order_data:
        try:
            payload = json.loads(request.body.decode('utf-8'))
            order_data = payload.get('order', [])
        except Exception:
            order_data = []

    try:
        coming_soon_service.reorder_features(order_data)
        return JsonResponse({'success': True, 'message': 'Feature card order updated successfully.'})
    except Exception:
        return JsonResponse({
            'success': False,
            'message': 'Database table has not been migrated yet. Please run "python manage.py migrate" first.'
        }, status=400)


@require_POST
def seed_default_features(request):
    """Seed or restore the 6 default features from the UI design."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    try:
        created_count = coming_soon_service.seed_default_features()

        return JsonResponse({
            'success': True,
            'message': f'Default features checked/seeded ({created_count} new features added).'
        })
    except Exception:
        return JsonResponse({
            'success': False,
            'message': 'Database table has not been migrated yet. Please run "python manage.py migrate" first.'
        }, status=400)


def save_coming_soon(request):
    """Legacy endpoint: Save Coming Soon HTML content for a given plan type (starter or professional)."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

    plan = request.POST.get('plan', '').strip().lower()
    html_content = request.POST.get('html_content', '').strip()

    if plan not in ('starter', 'professional'):
        return JsonResponse(
            {'success': False, 'message': 'Invalid plan type. Must be starter or professional.'},
            status=400
        )

    coming_soon_service.save_coming_soon_html(plan, html_content)

    plan_label = 'Starter' if plan == 'starter' else 'Professional'
    return JsonResponse({
        'success': True,
        'message': f'{plan_label} Plan Coming Soon content saved successfully!'
    })


@require_POST
def save_google_review_config(request):
    """Save global Google Review system config to SiteSetting."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    from apps.agents.services.google_review import save_google_review_system_config

    eligible_plans = request.POST.getlist('eligible_plans[]') or request.POST.getlist('eligible_plans')
    enabled = request.POST.get('enabled') in ('1', 'true', 'on', True)
    show_google_logo = request.POST.get('show_google_logo') in ('1', 'true', 'on', True)

    payload = {
        'enabled': enabled,
        'eligible_plans': eligible_plans,
        'max_reviews_shown': request.POST.get('max_reviews_shown', 5),
        'badge_style': request.POST.get('badge_style', 'compact'),
        'show_google_logo': show_google_logo,
        'badge_title': request.POST.get('badge_title', ''),
        'badge_subtitle': request.POST.get('badge_subtitle', ''),
        'cta_button_text': request.POST.get('cta_button_text', ''),
        'nudge_title': request.POST.get('nudge_title', ''),
        'nudge_message': request.POST.get('nudge_message', ''),
        'nudge_yes_text': request.POST.get('nudge_yes_text', ''),
        'nudge_skip_text': request.POST.get('nudge_skip_text', ''),
        'nudge_delay_ms': request.POST.get('nudge_delay_ms', 1200),
        'dashboard_section_title': request.POST.get('dashboard_section_title', ''),
        'dashboard_section_desc': request.POST.get('dashboard_section_desc', ''),
        'dashboard_url_placeholder': request.POST.get('dashboard_url_placeholder', ''),
    }

    try:
        saved = save_google_review_system_config(payload)
        return JsonResponse({
            'success': True,
            'message': 'Google Review system configuration updated successfully!',
            'config': saved
        })
    except Exception as e:
        logger.exception("Admin request failed in coming_soon")  # detail stays server-side
        return JsonResponse({'success': False, 'message': 'Failed to save. Details are in the server log.'}, status=500)


@require_POST
def toggle_google_review_system(request):
    """Quick ON/OFF toggle for the global Google Review system."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    try:
        saved = coming_soon_service.toggle_google_review_system()
        status_text = 'Enabled' if saved['enabled'] else 'Disabled'
        return JsonResponse({
            'success': True,
            'enabled': saved['enabled'],
            'message': f'Google Review system is now {status_text}.'
        })
    except Exception as e:
        logger.exception("Admin request failed in coming_soon")  # detail stays server-side
        return JsonResponse({'success': False, 'message': 'Error toggling. Details are in the server log.'}, status=500)
