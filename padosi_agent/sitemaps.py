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
        from apps.home.views.pages import MIN_INDEXABLE_CITY_AGENTS
        from django.utils.text import slugify
        # Only cities the city page itself marks indexable.
        cities = (City.objects.filter(is_active=True, agents__in=listed_agents_queryset().values('id'))
                .annotate(n=Count('agents', distinct=True))
                .filter(n__gte=MIN_INDEXABLE_CITY_AGENTS).order_by('name'))
        return [c for c in cities if _PROFILE_SLUG_RE.fullmatch(c.slug or slugify(c.name))]

    def location(self, obj):
        from django.utils.text import slugify
        slug = obj.slug or slugify(obj.name)
        return reverse('home:city_agents_directory', kwargs={'city_slug': slug})


sitemaps = {
    'static': StaticViewSitemap,
    'pages': PageSitemap,
    'calculators': CalculatorSitemap,
    'calculator_categories': CalculatorCategorySitemap,
    'cities': CitySitemap,
    'agents': AgentSitemap,
}

