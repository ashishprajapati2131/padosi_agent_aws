"""
Admin module #16 — Force-Update & App Version Control.

Lets a super-admin set, per platform (Android / iOS):
  - latest_version        (newest build on the store)
  - min_supported_version (oldest build allowed to keep running)
  - force_update          (hard-block below min_supported_version)
  - update_message        (text shown on the prompt)
  - store_url             (store link)
  - is_active             (feature on/off per platform)

The FastAPI mobile API (/api/v1/app/version) reads these rows.
"""
import re

from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST

from apps.admin_panel.models.app_version import AppVersion
from apps.admin_panel.models.admin_activity_log import AdminActivityLog
from apps.admin_panel.views.dashboard import _get_admin_from_session

VALID_PLATFORMS = {'android', 'ios'}
_VERSION_RE = re.compile(r'^\d+(\.\d+){0,3}$')


def _is_valid_version(v):
    return bool(v) and bool(_VERSION_RE.match(v.strip()))


def _version_tuple(v):
    """'1.4.0' -> (1, 4, 0). Tolerant of missing parts."""
    parts = []
    for p in (v or '').strip().split('.'):
        try:
            parts.append(int(p))
        except (TypeError, ValueError):
            parts.append(0)
    return tuple(parts)


def _ge(a, b):
    """a >= b, comparing version strings part-by-part."""
    ta, tb = _version_tuple(a), _version_tuple(b)
    length = max(len(ta), len(tb))
    ta = ta + (0,) * (length - len(ta))
    tb = tb + (0,) * (length - len(tb))
    return ta >= tb


def app_version_index(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    rows = {row.platform: row for row in AppVersion.objects.all()}
    platforms = [
        {'key': 'android', 'label': 'Android', 'row': rows.get('android')},
        {'key': 'ios', 'label': 'iOS', 'row': rows.get('ios')},
    ]
    return render(request, 'admin/app_version.html', {'platforms': platforms})


@require_POST
def app_version_save(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    platform = (request.POST.get('platform') or '').strip().lower()
    latest = (request.POST.get('latest_version') or '').strip()
    minimum = (request.POST.get('min_supported_version') or '').strip()
    force_update = request.POST.get('force_update') in ('1', 'on', 'true', 'True')
    is_active = request.POST.get('is_active') in ('1', 'on', 'true', 'True')
    update_message = (request.POST.get('update_message') or '').strip()[:255]
    store_url = (request.POST.get('store_url') or '').strip()[:500]

    if platform not in VALID_PLATFORMS:
        messages.error(request, 'Invalid platform.')
        return redirect('admin_app_version')

    if not _is_valid_version(latest) or not _is_valid_version(minimum):
        messages.error(request, 'Versions must look like 1.4.0 (digits and dots only).')
        return redirect('admin_app_version')

    if not _ge(latest, minimum):
        messages.error(request, 'Latest version cannot be lower than the minimum supported version.')
        return redirect('admin_app_version')

    row, _created = AppVersion.objects.get_or_create(
        platform=platform,
        defaults={'latest_version': latest, 'min_supported_version': minimum},
    )
    row.latest_version = latest
    row.min_supported_version = minimum
    row.force_update = force_update
    row.is_active = is_active
    row.update_message = update_message
    row.store_url = store_url
    row.save()

    AdminActivityLog.log(
        f'Updated {platform} app version (latest {latest}, min {minimum}, force={force_update})',
        'AppVersion', row.id, request=request,
    )
    messages.success(request, f'{platform.capitalize()} version settings saved.')
    return redirect('admin_app_version')
