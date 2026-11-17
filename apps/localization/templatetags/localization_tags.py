from urllib.parse import urlsplit, urlunsplit

from django import template
from django.utils import translation

from apps.localization import services

register = template.Library()


@register.filter
def localize_url(url):
    """Put the active language prefix into an absolute or root-relative URL (canonical tags)."""
    parts = urlsplit(str(url))
    path = services.localize_path(parts.path or "/", translation.get_language())
    return urlunsplit(parts._replace(path=path))


@register.filter
def translated(obj, field):
    """{{ page|translated:"title" }} -> approved translation for the active language, else the original."""
    return services.translated_field(obj, field, translation.get_language())
