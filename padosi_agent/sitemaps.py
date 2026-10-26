from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from apps.home.models.page import Page
from apps.home.models.calculator import Calculator
from apps.home.models.calculator_category import CalculatorCategory
from apps.agents.models import Agent
import re

# Mirrors the profile route regex: one bad slug must not 500 the whole sitemap.
_PROFILE_SLUG_RE = re.compile(r'[a-zA-Z0-9_-]+')

class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = 'weekly'

    def items(self):
        return ['home:home', 'home:about', 'home:faq', 'home:contact', 'home:terms', 'home:privacy', 'home:find_agents', 'home:calculators']

    def location(self, item):
        return reverse(item)

class PageSitemap(Sitemap):
    priority = 0.6
    changefreq = 'monthly'

    def items(self):
        return Page.objects.filter(is_active=True).order_by('id')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse('home:custom_page', kwargs={'slug': obj.slug})

class CalculatorSitemap(Sitemap):
    priority = 0.7
    changefreq = 'weekly'

    def items(self):
        return Calculator.objects.filter(is_active=True, engine_ready=True).order_by('id')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse('home:calculator_detail', kwargs={'slug': obj.slug})


class CalculatorCategorySitemap(Sitemap):
    priority = 0.65
    changefreq = 'weekly'

    def items(self):
        return CalculatorCategory.objects.filter(
            is_active=True,
            calculators__is_active=True,
            calculators__engine_ready=True,
        ).distinct().order_by('id')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse('home:calculator_detail', kwargs={'slug': obj.slug})

class AgentSitemap(Sitemap):
    priority = 0.9
    changefreq = 'daily'

    def items(self):
        # Same set the public directory lists (is_approved alone missed most
        # live profiles). Drop the directory's heavy prefetches; location()
        # only needs profile.
        from apps.home.services.agent_filters import listed_agents_queryset
        qs = listed_agents_queryset().prefetch_related(None).select_related('profile').order_by('id')
        return [a for a in qs if _PROFILE_SLUG_RE.fullmatch(a.agent_slug)]

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        state_code = getattr(obj, 'state_code', 'gj')
        if callable(state_code):
            state_code = state_code()
        slug = getattr(obj, 'agent_slug', str(obj.id))
        return reverse('agents:agent_public_profile_state_direct', kwargs={'state_code': state_code, 'slug': slug})

class CitySitemap(Sitemap):
    priority = 0.85
    changefreq = 'daily'

    def items(self):
        from django.db.models import Count
        from apps.agents.models import City
        from apps.home.services.agent_filters import listed_agents_queryset
        from apps.home.views.pages import JUNK_CITY_SLUGS, MIN_INDEXABLE_CITY_AGENTS
        from django.utils.text import slugify
        # Only cities the city page itself marks indexable.
        cities = (City.objects.filter(is_active=True, agents__in=listed_agents_queryset().values('id'))
                .annotate(n=Count('agents', distinct=True))
                .filter(n__gte=MIN_INDEXABLE_CITY_AGENTS).order_by('name'))
        return [c for c in cities if _PROFILE_SLUG_RE.fullmatch(c.slug or slugify(c.name))
                and (c.slug or slugify(c.name)) not in JUNK_CITY_SLUGS]

    def location(self, obj):
        from django.utils.text import slugify
        slug = obj.slug or slugify(obj.name)
        return reverse('home:city_agents_directory', kwargs={'city_slug': slug})

class CityCategorySitemap(Sitemap):
    """City x category / service pages, plus state hubs, that have listed agents."""
    priority = 0.8
    changefreq = 'daily'

    def items(self):
        from django.db.models import Count
        from apps.agents.models import City
        from apps.home.services.agent_filters import listed_agents_queryset
        from apps.home.views.pages import (CITY_CATEGORIES, JUNK_CITY_SLUGS, MIN_INDEXABLE_CITY_AGENTS, SERVICE_PAGES,
                                           STATE_HUBS, filter_agents_for_category, state_hub_agents)
        from django.utils.text import slugify
        listed = listed_agents_queryset()
        pages = {**CITY_CATEGORIES, **SERVICE_PAGES}
        items = []
        for key, category in pages.items():
            agent_ids = filter_agents_for_category(listed, category).values('id')
            cities = (City.objects.filter(is_active=True, agents__in=agent_ids)
                      .annotate(n=Count('agents', distinct=True))
                      .filter(n__gte=MIN_INDEXABLE_CITY_AGENTS).order_by('name'))
            for c in cities:
                slug = c.slug or slugify(c.name)
                if _PROFILE_SLUG_RE.fullmatch(slug) and slug not in STATE_HUBS and slug not in JUNK_CITY_SLUGS:
                    items.append((slug, key))
        for state_slug, hub in STATE_HUBS.items():
            in_state = state_hub_agents(listed, hub)
            for key in [None, *pages]:
                qs = filter_agents_for_category(in_state, pages[key]) if key else in_state
                if qs.count() >= MIN_INDEXABLE_CITY_AGENTS:
                    items.append((state_slug, key))
        return items

    def location(self, item):
        from apps.home.views.pages import _directory_path
        return _directory_path(*item)


sitemaps = {
    'static': StaticViewSitemap,
    'pages': PageSitemap,
    'calculators': CalculatorSitemap,
    'calculator_categories': CalculatorCategorySitemap,
    'cities': CitySitemap,
    'city_categories': CityCategorySitemap,
    'agents': AgentSitemap,
}

