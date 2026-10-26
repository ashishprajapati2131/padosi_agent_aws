"""Public site origin used in links inside WhatsApp messages."""
import os
from urllib.parse import urlparse

from django.conf import settings

from apps.agents.services.og_urls import CANONICAL_PADOSI_ORIGIN

_LOCAL_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0', '::1'}


def bot_site_url():
    """
    WA_BOT_SITE_URL, then APP_URL. A localhost value (e.g. copied from .env.example) is ignored
    outside DEBUG, so agents never receive links that only work on a developer machine.
    """
    for candidate in (os.environ.get('WA_BOT_SITE_URL', ''), getattr(settings, 'APP_URL', '')):
        url = (candidate or '').strip().rstrip('/')
        if url and (settings.DEBUG or (urlparse(url).hostname or '').lower() not in _LOCAL_HOSTS):
            return url
    return 'http://localhost:8000' if settings.DEBUG else CANONICAL_PADOSI_ORIGIN
