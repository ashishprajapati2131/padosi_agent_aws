"""
PWA endpoints — mirrors Laravel routes named pwa.manifest / pwa.sw / pwa.offline:

    GET /manifest.webmanifest  → application/manifest+json
    GET /sw.js                 → rendered service worker (Firebase injected)
    GET /offline.html          → static offline fallback page
"""

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import FileResponse, HttpResponse, Http404
from django.shortcuts import render


def _find_static_file(name):
    path = finders.find(name)
    if not path:
        path = (settings.BASE_DIR / 'static' / name)
        if not path.exists():
            raise Http404(f'{name} not found')
        path = str(path)
    return path


def manifest(request):
    try:
        return FileResponse(
            open(_find_static_file('manifest.webmanifest'), 'rb'),
            content_type='application/manifest+json',
        )
    except OSError:
        raise Http404('manifest not found')


def service_worker(request):
    from django.conf import settings as s
    return render(request, 'pwa/sw.html', {
        'fcm_api_key': s.FCM_API_KEY,
        'fcm_auth_domain': s.FCM_AUTH_DOMAIN,
        'fcm_project_id': s.FCM_PROJECT_ID,
        'fcm_storage_bucket': s.FCM_STORAGE_BUCKET,
        'fcm_messaging_sender_id': s.FCM_MESSAGING_SENDER_ID,
        'fcm_app_id': s.FCM_APP_ID,
    }, content_type='application/javascript')


def offline(request):
    try:
        return FileResponse(
            open(_find_static_file('offline.html'), 'rb'),
            content_type='text/html; charset=utf-8',
        )
    except OSError:
        raise Http404('offline page not found')