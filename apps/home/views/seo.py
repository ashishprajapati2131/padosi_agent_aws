from django.conf import settings
from django.http import Http404, HttpResponse


def indexnow_key(request, key):
    """IndexNow ownership proof: /<key>.txt must return the key itself."""
    if not settings.INDEXNOW_KEY or key != settings.INDEXNOW_KEY:
        raise Http404
    return HttpResponse(key, content_type='text/plain')
