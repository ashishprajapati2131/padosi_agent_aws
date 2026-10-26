from django.conf import settings
from django.http import Http404, HttpResponse


def indexnow_key(request, key):
    """IndexNow ownership proof: /<key>.txt must return the key itself."""
    if not settings.INDEXNOW_KEY or key != settings.INDEXNOW_KEY:
        raise Http404
    return HttpResponse(key, content_type='text/plain')

def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /django-admin/",
        "Disallow: /agent-login/",
        "Disallow: /agent/dashboard/",
        "Disallow: /insurance-login/",
        "Disallow: /media/app/private/",
        "Disallow: /api/",
        "",
        f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}"
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")
