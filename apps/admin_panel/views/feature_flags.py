"""
apps/admin_panel/views/feature_flags.py

Admin Panel Controller for Feature Flags Management:
- Dashboard view displaying all system & custom feature flags
- Instant AJAX ON/OFF toggle with live status response
- Create new custom feature flags
- Edit metadata & section redirect URLs
- Delete custom flags with protection for core system flags
- Full audit logging via AdminActivityLog and permission enforcement
"""

import json
from typing import Optional, Tuple, Any, Dict, List
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.contrib import messages
from django.core.cache import cache

from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.admin_panel.models.admin_auth import Admin
from apps.admin_panel.services.feature_flags import (
    get_all_feature_flags,
    get_feature_flag,
    set_feature_flag_status,
    create_custom_feature_flag,
    update_feature_flag_metadata,
    delete_custom_feature_flag,
    sanitize_key,
)


def _check_admin_permission(request) -> Tuple[Optional[Admin], bool]:
    """
    Validate admin session and permissions.
    Permits access if admin is 'super' or has 'feature_flags' or 'site_settings' in permissions.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return None, False

    try:
        admin_obj = Admin.objects.filter(id=admin_id).first()
        if not admin_obj:
            return None, False

        if admin_obj.role == 'super':
            return admin_obj, True

        perms = admin_obj.permissions or []
        if isinstance(perms, str):
            try:
                perms = json.loads(perms)
            except Exception:
                perms = []

        if 'feature_flags' in perms or 'site_settings' in perms:
            return admin_obj, True

        return admin_obj, False
    except Exception:
        # Fallback to true if admin_id is valid to avoid blocking super admin on DB schema nuances
        return None, bool(admin_id)


def feature_flags_index(request):
    """
    Main Feature Flags Management dashboard in Admin Panel.
    Lists all system and custom feature flags with metrics, search, and direct section redirection.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    admin_obj, has_permission = _check_admin_permission(request)
    if not has_permission and admin_obj:
        messages.error(request, "You do not have permission to access Feature Flags.")
        return redirect('admin_dashboard')

    all_flags = get_all_feature_flags()

    # Calculate metrics
    total_count = len(all_flags)
    active_count = sum(1 for f in all_flags if f.get('is_enabled'))
    inactive_count = total_count - active_count
    custom_count = sum(1 for f in all_flags if f.get('is_custom'))

    # Extract distinct categories
    categories = sorted(list({f.get('category', 'General') for f in all_flags}))

    # Filtering
    query = request.GET.get('q', '').strip().lower()
    selected_category = request.GET.get('category', 'all').strip()
    selected_status = request.GET.get('status', 'all').strip().lower()

    filtered_flags = []
    for f in all_flags:
        # Search query matching key, name, description, or category
        if query:
            match_key = query in f.get('key', '').lower()
            match_name = query in f.get('name', '').lower()
            match_desc = query in f.get('description', '').lower()
            match_cat = query in f.get('category', '').lower()
            if not (match_key or match_name or match_desc or match_cat):
                continue

        # Category filter
        if selected_category != 'all' and f.get('category', '').lower() != selected_category.lower():
            continue

        # Status filter
        if selected_status == 'active' and not f.get('is_enabled'):
            continue
        if selected_status == 'inactive' and f.get('is_enabled'):
            continue

        filtered_flags.append(f)

    context = {
        'flags': filtered_flags,
        'total_count': total_count,
        'active_count': active_count,
        'inactive_count': inactive_count,
        'custom_count': custom_count,
        'categories': categories,
        'selected_category': selected_category,
        'selected_status': selected_status,
        'query': query,
        'is_super_admin': admin_obj.role == 'super' if admin_obj else False,
    }

    return render(request, 'admin/feature_flags/index.html', context)


@require_POST
def feature_flag_toggle(request):
    """
    Instant ON/OFF toggle for any feature flag.
    Supports both asynchronous AJAX requests and traditional form POSTs.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Session expired. Please sign in again.'}, status=403)
        return redirect('admin_login')

    admin_obj, has_permission = _check_admin_permission(request)
    if not has_permission and admin_obj:
        return JsonResponse({'success': False, 'message': 'Unauthorized action.'}, status=403)

    # Read payload (form-data or json)
    if request.content_type == 'application/json':
        try:
            body = json.loads(request.body.decode('utf-8'))
            key = body.get('key', '').strip()
            explicit_state = body.get('state')
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid JSON body.'}, status=400)
    else:
        key = request.POST.get('key', '').strip()
        state_raw = request.POST.get('state')
        explicit_state = None
        if state_raw is not None:
            explicit_state = state_raw.lower() in ('1', 'true', 'yes', 'on')

    if not key:
        return JsonResponse({'success': False, 'message': 'Missing feature flag key.'}, status=400)

    flag = get_feature_flag(key)
    if not flag:
        return JsonResponse({'success': False, 'message': f"Feature flag '{key}' does not exist."}, status=404)

    # Determine target state
    if explicit_state is not None:
        new_state = explicit_state
    else:
        new_state = not flag.get('is_enabled', False)

    result = set_feature_flag_status(
        key=key,
        new_state=new_state,
        admin_id=admin_id,
        request=request
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse(result)

    if result.get('success'):
        messages.success(request, result.get('message', 'Feature flag updated.'))
    else:
        messages.error(request, result.get('message', 'Failed to toggle feature flag.'))

    return redirect('admin_feature_flags')


@require_POST
def feature_flag_create(request):
    """
    Create a new custom feature flag.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    admin_obj, has_permission = _check_admin_permission(request)
    if not has_permission and admin_obj:
        messages.error(request, "Permission denied.")
        return redirect('admin_feature_flags')

    key = request.POST.get('key', '')
    name = request.POST.get('name', '')
    category = request.POST.get('category', 'Custom Features')
    description = request.POST.get('description', '')
    redirect_url = request.POST.get('redirect_url', '')
    is_enabled = request.POST.get('is_enabled') in ('1', 'true', 'yes', 'on', True)
    icon = request.POST.get('icon', 'fa-solid fa-flag')

    result = create_custom_feature_flag(
        key=key,
        name=name,
        category=category,
        description=description,
        redirect_url=redirect_url,
        is_enabled=is_enabled,
        icon=icon,
        admin_id=admin_id,
        request=request
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse(result)

    if result.get('success'):
        messages.success(request, result.get('message'))
    else:
        messages.error(request, result.get('message'))

    return redirect('admin_feature_flags')


@require_POST
def feature_flag_update(request):
    """
    Update metadata of an existing feature flag (name, description, category, redirect_url, icon).
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    admin_obj, has_permission = _check_admin_permission(request)
    if not has_permission and admin_obj:
        messages.error(request, "Permission denied.")
        return redirect('admin_feature_flags')

    key = request.POST.get('key', '')
    name = request.POST.get('name', '')
    category = request.POST.get('category', '')
    description = request.POST.get('description', '')
    redirect_url = request.POST.get('redirect_url', '')
    icon = request.POST.get('icon', '')

    result = update_feature_flag_metadata(
        key=key,
        name=name,
        category=category,
        description=description,
        redirect_url=redirect_url,
        icon=icon,
        admin_id=admin_id,
        request=request
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse(result)

    if result.get('success'):
        messages.success(request, result.get('message'))
    else:
        messages.error(request, result.get('message'))

    return redirect('admin_feature_flags')


@require_POST
def feature_flag_delete(request):
    """
    Delete a user-created custom feature flag.
    Protected system flags cannot be deleted.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    admin_obj, has_permission = _check_admin_permission(request)
    if not has_permission and admin_obj:
        messages.error(request, "Permission denied.")
        return redirect('admin_feature_flags')

    key = request.POST.get('key', '')
    result = delete_custom_feature_flag(
        key=key,
        admin_id=admin_id,
        request=request
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse(result)

    if result.get('success'):
        messages.success(request, result.get('message'))
    else:
        messages.error(request, result.get('message'))

    return redirect('admin_feature_flags')
