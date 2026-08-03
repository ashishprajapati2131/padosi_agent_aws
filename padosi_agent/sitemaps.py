from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from apps.home.models.page import Page
from apps.agents.models import Agent

class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = 'weekly'

    def items(self):
        return ['home:home', 'home:about', 'home:faq', 'home:contact', 'home:terms', 'home:privacy', 'home:find_agents']

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

class AgentSitemap(Sitemap):
    priority = 0.9
    changefreq = 'daily'

    def items(self):
        return Agent.objects.filter(is_approved=True, status='active')

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        # We need to construct the URL for the agent profile
        # The URL name is 'agents:agent_public_profile' (or 'agents:agent_public_share_profile' which is the same)
        return reverse('agents:agent_public_profile', kwargs={'slug': obj.agent_slug})

sitemaps = {
    'static': StaticViewSitemap,
    'pages': PageSitemap,
    'agents': AgentSitemap,
}
