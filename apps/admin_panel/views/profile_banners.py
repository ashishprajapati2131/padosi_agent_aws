import os
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db.models import Count

from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.admin_panel.models.admin_activity_log import AdminActivityLog
from apps.admin_panel.services import profile_banners_service
from apps.agents.models import ProfileBannerPreset, AgentProfile
from apps.home.models.site_setting import SiteSetting
from apps.agents.utils.file_validation import validate_profile_photo, file_basename, has_dangerous_extra_extension


def _validate_preset_image(file_bytes, filename):
    if not file_bytes:
        return False, "File is empty.", None
    if len(file_bytes) > 10 * 1024 * 1024:
        return False, "Banner image must be under 10MB.", None
    base = file_basename(filename)
    if not base or has_dangerous_extra_extension(base):
        return False, "Invalid file name.", None
    
    ext = os.path.splitext(base.lower())[1]
    if ext == '.svg':
        # Comprehensive SVG Security Audit & Disinfection
        try:
            content_str = file_bytes.decode('utf-8', errors='ignore')
            content_lower = content_str.lower()

            # 1. Defend against XXE (XML External Entity attack)
            if '<!doctype' in content_lower or '<!entity' in content_lower:
                return False, "SVG files with DTD/ENTITY declarations are prohibited for security.", None

            # 2. Block executable and media-embedding tags
            dangerous_tags = ['<script', '<foreignobject', '<iframe', '<embed', '<object', '<audio', '<video', '<applet']
            if any(tag in content_lower for tag in dangerous_tags):
                return False, "SVG contains disallowed executable elements.", None

            # 3. Block all DOM inline event handlers (on* attributes like onload, onerror, onclick, onbegin)
            if re.search(r'\bon[a-zA-Z]+\s*=', content_str, re.IGNORECASE):
                return False, "SVG contains inline event handler attributes.", None

            # 4. Block dangerous script URL schemes (javascript:, vbscript:, data:text/html)
            if re.search(r'(javascript|vbscript|data\s*:\s*text/html)\s*:', content_lower):
                return False, "SVG contains insecure URL schemes.", None

            # 5. Must contain valid root svg tag
            if '<svg' not in content_lower:
                return False, "File does not contain a valid SVG root element.", None

            # 6. Verify well-formed XML parsing without external entities
            import xml.etree.ElementTree as ET
            ET.fromstring(file_bytes)
            return True, None, '.svg'
        except Exception:
            return False, "Corrupted or non-parseable XML/SVG file.", None

    # Normal raster images (JPG, PNG, WEBP, GIF): strictly validated by Pillow
    ok, err, safe_ext = validate_profile_photo(file_bytes, filename)
    return ok, err, safe_ext


def profile_banners_index(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    presets = ProfileBannerPreset.objects.annotate(
        agents_count=Count('agent_profiles')
    ).order_by('display_order', '-created_at')

    total_presets = presets.count()
    active_presets = presets.filter(is_active=True).count()
    
    banner_enabled_val = SiteSetting.get_value('profile_banner_enabled', '1')
    banner_enabled = str(banner_enabled_val).lower() in ('1', 'true', 'yes')

    allow_custom_val = SiteSetting.get_value('profile_banner_allow_custom_upload', '1')
    allow_custom = str(allow_custom_val).lower() in ('1', 'true', 'yes')

    # Count how many agents currently have a banner (either preset or custom)
    agents_with_banner_count = AgentProfile.objects.filter(
        banner_preset__isnull=False
    ).count() + AgentProfile.objects.filter(
        custom_banner_path__isnull=False,
        banner_preset__isnull=True
    ).exclude(custom_banner_path='').count()

    context = {
        'presets': presets,
        'total_presets': total_presets,
        'active_presets': active_presets,
        'banner_enabled': banner_enabled,
        'allow_custom': allow_custom,
        'agents_with_banner_count': agents_with_banner_count,
    }
    return render(request, 'admin/profile_banners/index.html', context)


@require_POST
def profile_banner_upload(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    title = (request.POST.get('title') or '').strip()
    category = (request.POST.get('category') or 'General').strip()
    display_order = request.POST.get('display_order', 0)
    banner_file = request.FILES.get('banner_image')

    if not title:
        messages.error(request, "Banner title is required.")
        return redirect('admin_profile_banners_index')
    if len(title) > 100 or re.search(r'[<>]', title):
        messages.error(request, "Banner title cannot contain HTML or exceed 100 characters.")
        return redirect('admin_profile_banners_index')
    if len(category) > 50 or re.search(r'[<>]', category):
        messages.error(request, "Category cannot contain HTML or exceed 50 characters.")
        return redirect('admin_profile_banners_index')

    if not banner_file:
        messages.error(request, "Please choose a banner image file.")
        return redirect('admin_profile_banners_index')

    try:
        display_order = int(display_order)
    except (ValueError, TypeError):
        display_order = 0

    file_bytes = b''.join(banner_file.chunks())
    ok, err, safe_ext = _validate_preset_image(file_bytes, banner_file.name)
    if not ok:
        messages.error(request, err or "Invalid image file.")
        return redirect('admin_profile_banners_index')

    preset = profile_banners_service.create_preset(title, category, display_order, file_bytes, safe_ext)

    AdminActivityLog.log(
        f"Uploaded profile banner preset: {preset.title}",
        "ProfileBannerPreset",
        preset.id,
        request=request
    )

    messages.success(request, f"Banner preset '{preset.title}' uploaded successfully.")
    return redirect('admin_profile_banners_index')


@require_POST
def profile_banner_toggle(request, banner_id):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    preset = get_object_or_404(ProfileBannerPreset, id=banner_id)
    profile_banners_service.toggle_preset(preset)

    status_str = "activated" if preset.is_active else "deactivated"
    AdminActivityLog.log(
        f"{status_str.capitalize()} profile banner preset: {preset.title}",
        "ProfileBannerPreset",
        preset.id,
        request=request
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({
            'success': True,
            'is_active': preset.is_active,
            'message': f"Banner '{preset.title}' {status_str}."
        })

    messages.success(request, f"Banner '{preset.title}' {status_str}.")
    return redirect('admin_profile_banners_index')


@require_POST
def profile_banner_delete(request, banner_id):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    preset = get_object_or_404(ProfileBannerPreset, id=banner_id)
    title = preset.title
    preset_id = preset.id

    profile_banners_service.delete_preset(preset)

    AdminActivityLog.log(
        f"Deleted profile banner preset: {title}",
        "ProfileBannerPreset",
        preset_id,
        request=request
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': f"Banner '{title}' deleted."})

    messages.success(request, f"Banner '{title}' deleted successfully.")
    return redirect('admin_profile_banners_index')


@require_POST
def profile_banner_settings_save(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    banner_enabled = '1' if request.POST.get('profile_banner_enabled') in ('1', 'on', 'true') else '0'
    allow_custom = '1' if request.POST.get('profile_banner_allow_custom_upload') in ('1', 'on', 'true') else '0'

    profile_banners_service.save_banner_settings(banner_enabled, allow_custom)

    AdminActivityLog.log(
        f"Updated profile banner feature flags: enabled={banner_enabled}, allow_custom={allow_custom}",
        "SiteSetting",
        request=request
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': 'Banner settings updated successfully.',
            'profile_banner_enabled': banner_enabled == '1',
            'profile_banner_allow_custom_upload': allow_custom == '1',
        })

    messages.success(request, "Banner feature settings updated successfully.")
    return redirect('admin_profile_banners_index')
