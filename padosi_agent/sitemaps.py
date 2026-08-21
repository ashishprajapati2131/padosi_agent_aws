from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from apps.home.models.page import Page
from apps.home.models.calculator import Calculator
from apps.home.models.calculator_category import CalculatorCategory
from apps.agents.models import Agent

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
        return Page.objects.filter(is_active=True)

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse('home:custom_page', kwargs={'slug': obj.slug})

class CalculatorSitemap(Sitemap):
    priority = 0.7
    changefreq = 'weekly'

    def items(self):
        return Calculator.objects.filter(is_active=True, engine_ready=True)

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
        ).distinct()

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse('home:calculator_detail', kwargs={'slug': obj.slug})

class AgentSitemap(Sitemap):
    priority = 0.9
    changefreq = 'daily'

    def items(self):
        return Agent.objects.filter(is_approved=True, status='active')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse('agents:agent_public_profile', kwargs={'slug': obj.agent_slug})

sitemaps = {
    'static': StaticViewSitemap,
    'pages': PageSitemap,
    'calculators': CalculatorSitemap,
    'calculator_categories': CalculatorCategorySitemap,
    'agents': AgentSitemap,
}
