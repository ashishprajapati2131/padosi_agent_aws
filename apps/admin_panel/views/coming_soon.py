from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from apps.admin_panel.views.dashboard import _get_admin_from_session
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


def _auto_seed_if_empty():
    """Seed initial screenshot features if table is empty."""
    try:
        if UpcomingFeature.objects.count() == 0:
            for item in DEFAULT_FEATURES:
                UpcomingFeature.objects.create(**item)
    except Exception:
        pass


def coming_soon_index(request):
    """Admin page to manage dynamic Coming Soon features + legacy HTML content."""
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    table_exists = True
    try:
        _auto_seed_if_empty()
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

    return render(request, 'admin/coming_soon/index.html', {
        'features': features,
        'total_count': total_count,
        'active_count': active_count,
        'starter_count': starter_count,
        'pro_count': pro_count,
        'table_exists': table_exists,
        'coming_soon_starter_html': coming_soon_starter_html,
        'coming_soon_professional_html': coming_soon_professional_html,
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
            feature.title = title
            feature.description = description
            feature.icon = icon
            feature.status_badge = status_badge
            feature.custom_badge_text = custom_badge_text
            feature.visible_to = visible_to
            feature.sort_order = sort_order
            feature.is_active = is_active
            feature.save()
            action_msg = 'Feature updated successfully!'
        else:
            if sort_order == 0:
                last = UpcomingFeature.objects.order_by('-sort_order').first()
                sort_order = (last.sort_order + 1) if last else 1

            feature = UpcomingFeature.objects.create(
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
    except Exception as e:
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
        feature.is_active = not feature.is_active
        feature.save(update_fields=['is_active'])

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
        title = feature.title
        feature.delete()

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
        for index, fid in enumerate(order_data, 1):
            try:
                UpcomingFeature.objects.filter(id=int(fid)).update(sort_order=index)
            except (ValueError, TypeError):
                continue
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
        created_count = 0
        for item in DEFAULT_FEATURES:
            _, created = UpcomingFeature.objects.get_or_create(
                title=item['title'],
                defaults=item
            )
            if created:
                created_count += 1

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

    setting_key = f'coming_soon_{plan}_html'
    SiteSetting.set_value(setting_key, html_content, group='coming_soon')

    plan_label = 'Starter' if plan == 'starter' else 'Professional'
    return JsonResponse({
        'success': True,
        'message': f'{plan_label} Plan Coming Soon content saved successfully!'
    })
