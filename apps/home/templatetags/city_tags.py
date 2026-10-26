import logging
import re

from django import template
from django.core.cache import cache

register = template.Library()
logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r'[a-zA-Z0-9_-]+')
POPULAR_CITIES_CACHE_KEY = 'footer_popular_cities'


@register.simple_tag
def popular_cities(limit=8, min_agents=3):
    """Cities with the most listed agents, for crawlable footer links.

    min_agents keeps one-agent free-text entries ("all world") out. Cached for
    an hour; any error returns [] so the footer always renders.
    """
    cities = cache.get(POPULAR_CITIES_CACHE_KEY)
    if cities is not None:
        return cities
    try:
        from django.db.models import Count
        from django.utils.text import slugify
        from apps.agents.models import City
        from apps.home.services.agent_filters import listed_agents_queryset

        rows = (City.objects.filter(is_active=True, agents__in=listed_agents_queryset().values('id'))
                .annotate(n=Count('agents', distinct=True))
                .filter(n__gte=min_agents)
                .order_by('-n', 'name')[:limit])
        cities = []
        for c in rows:
            slug = c.slug or slugify(c.name)
            if _SLUG_RE.fullmatch(slug):
                cities.append({'name': c.name.strip().title(), 'slug': slug})
    except Exception:
        logger.exception('popular_cities failed')
        return []
    cache.set(POPULAR_CITIES_CACHE_KEY, cities, 3600)
    return cities
