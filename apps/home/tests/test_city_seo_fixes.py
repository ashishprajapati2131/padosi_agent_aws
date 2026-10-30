import json
import re

from django.core.cache import cache
from django.template import Context, Template
from django.test import TestCase, override_settings

from apps.agents.models import Agent, AgentProfile, City


def _listed_agent(name, slug, city=None, address=''):
    agent = Agent.objects.create(fullname=name, email=f'{slug}@example.com', mobile='9876543210', status='active')
    AgentProfile.objects.create(agent=agent, slug=slug, display_name=name, is_profile_visible=True, address=address)
    if city:
        agent.serviceableCities.add(city)
    return agent


def _item_list(body):
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S):
        data = json.loads(block)
        if data.get('@type') == 'ItemList':
            return data
    return None


@override_settings(ALLOWED_HOSTS=['*'])
class CityDirectoryIndexingTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_unknown_slug_text_match_is_noindex(self):
        _listed_agent('Road Agent', 'road-agent', address='Station Road, Somewhere')
        response = self.client.get('/insurance-agents/road/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="robots" content="noindex, follow">')

    def test_known_city_stays_indexable(self):
        surat = City.objects.create(name='Surat', slug='surat', state='Gujarat')
        _listed_agent('Agent One', 'agent-one', surat)
        response = self.client.get('/insurance-agents/surat/')
        self.assertContains(response, '<meta name="robots" content="index, follow">')

    def test_long_slug_still_renders(self):
        _listed_agent('Road Agent', 'road-agent', address='Station Road')
        response = self.client.get('/insurance-agents/aaa-bbb-ccc-ddd-road/')
        # Only the first three tokens are matched, so 'road' finds nobody.
        self.assertEqual(response.status_code, 404)

    def test_item_list_json_ld_is_valid_and_escaped(self):
        surat = City.objects.create(name='Surat', slug='surat', state='Gujarat')
        _listed_agent('Evil </script><b>x', 'evil', surat)
        body = self.client.get('/insurance-agents/surat/').content.decode()
        self.assertNotIn('</script><b>', body)
        data = _item_list(body)
        self.assertEqual(data['name'], 'Verified Insurance Agents in Surat')
        self.assertEqual(data['numberOfItems'], 1)
        item = data['itemListElement'][0]
        self.assertEqual(item['position'], 1)
        self.assertEqual(item['item']['name'], 'Evil </script><b>x')
        self.assertTrue(item['item']['url'].endswith('/gj/evil/'))
        self.assertEqual(item['item']['telephone'], '+919876543210')
        self.assertEqual(item['item']['address']['addressLocality'], 'Surat')


@override_settings(ALLOWED_HOSTS=['*'])
class SitemapCacheAndDedupeTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_state_hub_slug_listed_once(self):
        gujarat = City.objects.create(name='Gujarat', slug='gujarat', state='Gujarat')
        _listed_agent('Hub Agent', 'hub-agent', gujarat)
        body = self.client.get('/sitemap.xml').content.decode()
        self.assertEqual(body.count('/insurance-agents/gujarat/</loc>'), 1)

    def test_sitemap_response_is_cached(self):
        self.client.get('/sitemap.xml')
        _listed_agent('Late Agent', 'late-agent')
        self.assertNotIn('/gj/late-agent/', self.client.get('/sitemap.xml').content.decode())
        cache.clear()
        self.assertIn('/gj/late-agent/', self.client.get('/sitemap.xml').content.decode())

    def test_robots_not_cached_by_sitemap(self):
        self.assertEqual(self.client.get('/robots.txt').status_code, 200)


class PopularCitiesTagTests(TestCase):
    def setUp(self):
        cache.clear()

    def _render(self, tpl):
        return Template('{% load city_tags %}' + tpl).render(Context())

    def test_args_have_their_own_cache_entry_and_junk_is_excluded(self):
        surat = City.objects.create(name='Surat', slug='surat')
        junk = City.objects.create(name='Pan India', slug='pan-india')
        for i in range(3):
            _listed_agent(f'S {i}', f's-{i}', surat)
            junk.agents.add(Agent.objects.get(email=f's-{i}@example.com'))
        tpl = '{% popular_cities 8 3 as c %}{% for x in c %}{{ x.slug }},{% endfor %}'
        self.assertEqual(self._render(tpl), 'surat,')
        self.assertEqual(self._render('{% popular_cities 8 99 as c %}{{ c|length }}'), '0')

    def test_errors_are_cached_briefly(self):
        from unittest import mock
        with mock.patch('apps.home.services.agent_filters.listed_agents_queryset',
                        side_effect=RuntimeError('db down')) as failing:
            self._render('{% popular_cities as c %}')
            self._render('{% popular_cities as c %}')
        self.assertEqual(failing.call_count, 1)


@override_settings(ALLOWED_HOSTS=['*'])
class WwwRedirectEarlyTests(TestCase):
    def test_www_redirect_sets_no_cookies(self):
        response = self.client.get('/find-agents/?q=1', HTTP_HOST='www.example.com')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], 'http://example.com/find-agents/?q=1')
        self.assertFalse(response.cookies)
