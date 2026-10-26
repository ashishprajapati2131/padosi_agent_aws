from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.agents.models import Agent, AgentProfile, City


def _listed_agent(name, slug, city=None):
    agent = Agent.objects.create(fullname=name, email=f'{slug}@example.com', mobile='9876543210', status='active')
    AgentProfile.objects.create(agent=agent, slug=slug, display_name=name, is_profile_visible=True)
    if city:
        agent.serviceableCities.add(city)
    return agent


@override_settings(ALLOWED_HOSTS=['*'])
class CityDirectorySeoTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_locality_page_renders_instead_of_500(self):
        # 'thaltej' is in _AREA_PINCODE_MAP; the pincode filter used a field that does not exist.
        response = self.client.get('/insurance-agents/thaltej/')
        self.assertEqual(response.status_code, 200)

    def test_unknown_city_is_404(self):
        response = self.client.get('/insurance-agents/xyzabc/')
        self.assertEqual(response.status_code, 404)

    def test_empty_city_is_noindex_and_city_with_agent_is_indexed(self):
        surat = City.objects.create(name='Surat', slug='surat', state='Gujarat')
        response = self.client.get('/insurance-agents/surat/')
        self.assertContains(response, '<meta name="robots" content="noindex, follow">')

        _listed_agent('Agent One', 'agent-one', surat)
        cache.clear()
        response = self.client.get('/insurance-agents/surat/')
        self.assertContains(response, '<meta name="robots" content="index, follow">')
        self.assertNotContains(response, '"postalCode": "380001"')

    def test_sitemap_lists_directory_agents_and_cities(self):
        ahmedabad = City.objects.create(name='Ahmedabad', slug='ahmedabad', state='Gujarat')
        # is_approved defaults to False, as for most live listed agents.
        _listed_agent('Listed 0', 'listed-0', ahmedabad)
        bad = _listed_agent('Bad Slug', 'bad.slug', ahmedabad)
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('/gj/listed-0/', body)
        self.assertIn('/insurance-agents/ahmedabad/', body)
        self.assertNotIn(bad.profile.slug, body)


@override_settings(ALLOWED_HOSTS=['*'])
class CityCategoryDirectoryTests(TestCase):
    def setUp(self):
        cache.clear()
        from apps.agents.models import AgentInsuranceSegment
        self.city = City.objects.create(name='Ahmedabad', slug='ahmedabad', state='Gujarat')
        health = _listed_agent('Health Agent', 'health-agent', self.city)
        AgentInsuranceSegment.objects.create(agent=health, segment_type='health')
        motor = _listed_agent('Motor Agent', 'motor-agent', self.city)
        AgentInsuranceSegment.objects.create(agent=motor, segment_type='motor')

    def test_category_page_filters_by_segment(self):
        response = self.client.get('/insurance-agents/ahmedabad/health-insurance/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Top-Rated Health Insurance Agents in Ahmedabad, Gujarat')
        self.assertContains(response, 'health-agent')
        self.assertNotContains(response, 'motor-agent')
        self.assertContains(response, '"@type": "FAQPage"')
        self.assertContains(response, '<meta name="robots" content="index, follow">')
        self.assertRegex(response.content.decode(),
                         r'<link rel="canonical" href="https?://[^"]+/insurance-agents/ahmedabad/health-insurance/">')

    def test_empty_category_is_noindex(self):
        response = self.client.get('/insurance-agents/ahmedabad/business-insurance/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<meta name="robots" content="noindex, follow">')

    def test_unknown_category_and_unknown_city_are_404(self):
        self.assertEqual(self.client.get('/insurance-agents/ahmedabad/pet-insurance/').status_code, 404)
        self.assertEqual(self.client.get('/insurance-agents/xyzabc/health-insurance/').status_code, 404)

    def test_city_page_still_lists_all_and_links_categories(self):
        response = self.client.get('/insurance-agents/ahmedabad/')
        self.assertContains(response, 'Verified Insurance Agents in Ahmedabad</h1>')
        self.assertContains(response, 'health-agent')
        self.assertContains(response, 'motor-agent')
        self.assertContains(response, 'href="/insurance-agents/ahmedabad/health-insurance/"')
        self.assertNotContains(response, 'FAQPage')

    def test_sitemap_lists_only_categories_with_agents(self):
        body = self.client.get('/sitemap.xml').content.decode()
        self.assertIn('/insurance-agents/ahmedabad/health-insurance/', body)
        self.assertIn('/insurance-agents/ahmedabad/motor-insurance/', body)
        self.assertNotIn('/insurance-agents/ahmedabad/business-insurance/', body)

    def _json_ld(self, response):
        import json, re
        return [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                                                  response.content.decode(), re.S)]

    def test_city_hub_has_breadcrumb_schema(self):
        blocks = self._json_ld(self.client.get('/insurance-agents/ahmedabad/'))
        crumbs = [b for b in blocks if b.get('@type') == 'BreadcrumbList']
        self.assertEqual(len(crumbs), 1)
        items = crumbs[0]['itemListElement']
        self.assertEqual([i['name'] for i in items], ['Home', 'Insurance Agents', 'Ahmedabad'])
        self.assertTrue(items[2]['item'].endswith('/insurance-agents/ahmedabad/'))

        blocks = self._json_ld(self.client.get('/insurance-agents/ahmedabad/health-insurance/'))
        crumbs = [b for b in blocks if b.get('@type') == 'BreadcrumbList']
        self.assertEqual(len(crumbs), 1)
        self.assertEqual(crumbs[0]['itemListElement'][3]['name'], 'Health Insurance Agents')

    def test_find_agents_template_has_valid_json_ld(self):
        import json, re
        from django.template.loader import render_to_string
        from django.test import RequestFactory
        html = render_to_string('public/find-agents.html', {}, request=RequestFactory().get('/find-agents/'))
        blocks = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
        types = {node['@type'] for b in blocks for node in b.get('@graph', [b])}
        self.assertIn('CollectionPage', types)
        self.assertIn('BreadcrumbList', types)

    def test_junk_city_stays_up_but_noindex_and_out_of_sitemap(self):
        world = City.objects.create(name='All World', slug='all-world')
        _listed_agent('World Agent', 'world-agent', world)
        for path in ('/insurance-agents/all-world/', '/insurance-claim-assistance/all-world/'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertContains(response, '<meta name="robots" content="noindex, follow">')
        body = self.client.get('/sitemap.xml').content.decode()
        self.assertNotIn('all-world', body)
        self.assertIn('/insurance-agents/ahmedabad/', body)

    def _lic_agent(self):
        from apps.agents.models import AgentPortfolio
        lic = _listed_agent('Lic Agent', 'lic-agent', self.city)
        AgentPortfolio.objects.create(agent=lic, segment_type='life',
                                      primary_companies={'name': 'Life Insurance Corporation of India', 'percentage': '100'})
        return lic

    def test_lic_page_lists_only_lic_agents(self):
        self._lic_agent()
        response = self.client.get('/insurance-agents/ahmedabad/lic-agents/')
        self.assertContains(response, 'Top-Rated LIC Agents in Ahmedabad, Gujarat')
        self.assertContains(response, 'lic-agent')
        self.assertNotContains(response, 'health-agent')
        self.assertContains(response, 'Looking for a trusted LIC agent')

    def test_service_pages_list_all_city_agents(self):
        for path, heading in (('/insurance-claim-assistance/ahmedabad/', 'Insurance Claim Assistance'),
                              ('/insurance-renewal/ahmedabad/', 'Insurance Policy Renewal')):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertContains(response, f'Top-Rated {heading} Agents in Ahmedabad')
            self.assertContains(response, 'health-agent')
            self.assertContains(response, 'motor-agent')
            self.assertRegex(response.content.decode(), r'<link rel="canonical" href="https?://[^"]+' + path + '">')
        self.assertEqual(self.client.get('/insurance-claim-assistance/xyzabc/').status_code, 404)

    def test_gujarat_hub_lists_state_agents_and_cities(self):
        # Live cities mostly have no state saved; the hub must still find them.
        City.objects.filter(pk=self.city.pk).update(state=None)
        mumbai = City.objects.create(name='Mumbai', slug='mumbai', state='Maharashtra')
        _listed_agent('Mumbai Agent', 'mumbai-agent', mumbai)
        pin_only = _listed_agent('Pin Agent', 'pin-agent')
        Agent.objects.filter(pk=pin_only.pk).update(agent_pincode='395007')
        response = self.client.get('/insurance-agents/gujarat/')
        self.assertContains(response, 'Verified Insurance Agents in Gujarat</h1>')
        self.assertContains(response, '<meta name="robots" content="index, follow">')
        self.assertContains(response, 'health-agent')
        self.assertContains(response, 'pin-agent')
        self.assertNotContains(response, 'mumbai-agent')
        self.assertContains(response, 'href="/insurance-agents/ahmedabad/"')

        response = self.client.get('/insurance-agents/gujarat/health-insurance/')
        self.assertContains(response, 'Top-Rated Health Insurance Agents in Gujarat, India')
        self.assertNotContains(response, 'motor-agent')
        self.assertContains(response, 'href="/insurance-agents/ahmedabad/health-insurance/"')

    def test_sitemap_lists_services_lic_and_state_hub(self):
        self._lic_agent()
        body = self.client.get('/sitemap.xml').content.decode()
        for path in ('/insurance-agents/ahmedabad/lic-agents/', '/insurance-claim-assistance/ahmedabad/',
                     '/insurance-renewal/ahmedabad/', '/insurance-agents/gujarat/',
                     '/insurance-agents/gujarat/health-insurance/', '/insurance-claim-assistance/gujarat/'):
            self.assertIn(path, body)
        self.assertNotIn('/insurance-agents/gujarat/business-insurance/', body)


@override_settings(ALLOWED_HOSTS=['*'])
class SeoRedirectTests(TestCase):
    def test_insurance_agents_hub_redirects_to_find_agents(self):
        response = self.client.get('/insurance-agents/?location=surat')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/find-agents/?location=surat')

    def test_legacy_calculator_redirects_to_hub(self):
        response = self.client.get('/calculator/')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], '/calculators/')

    def test_www_get_redirects_to_bare_host(self):
        response = self.client.get('/about/?a=1', HTTP_HOST='www.example.com')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], 'http://example.com/about/?a=1')

    def test_www_post_is_not_redirected(self):
        response = self.client.post('/contact/submit/', HTTP_HOST='www.example.com')
        self.assertNotEqual(response.status_code, 301)


@override_settings(ALLOWED_HOSTS=['*'])
class LegalPageMetaTests(TestCase):
    def test_legal_pages_have_description_and_absolute_canonical(self):
        for path in ('/terms/', '/privacy/', '/cancellation-refund-policy/'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            body = response.content.decode()
            self.assertEqual(body.count('<meta name="description"'), 1, path)
            # Host comes from APP_URL (get_public_site_base), so only check shape.
            self.assertRegex(body, r'<link rel="canonical" href="https?://[^/"]+' + path + '">')


class NoindexPathTests(TestCase):
    # Middleware tested directly: /find-agents/ views use MySQL-only SQL that
    # the SQLite test database cannot run.
    def _robots_header(self, path):
        from django.http import HttpResponse
        from django.test import RequestFactory
        from padosi_agent.middleware import SEOMiddleware
        mw = SEOMiddleware(lambda request: HttpResponse('ok'))
        return mw(RequestFactory().get(path)).get('X-Robots-Tag')

    def test_placeholder_pages_send_noindex_header(self):
        for path in ('/coming-soon/', '/find-agents/ai-picks/', '/agent-login/'):
            self.assertEqual(self._robots_header(path), 'noindex, nofollow', path)

    def test_public_pages_stay_indexable(self):
        for path in ('/', '/find-agents/', '/about/', '/insurance-agents/surat/'):
            self.assertIsNone(self._robots_header(path), path)


@override_settings(ALLOWED_HOSTS=['*'])
class BlacklistedPageTests(TestCase):
    def test_has_one_h1_and_own_description(self):
        response = self.client.get('/blacklisted-agents/')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertEqual(body.count('<h1'), 1)
        self.assertIn('<meta name="description" content="Check whether an insurance agent has been blacklisted', body)


@override_settings(ALLOWED_HOSTS=['*'])
class FooterPopularCitiesTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_footer_links_cities_with_three_or_more_agents(self):
        surat = City.objects.create(name='Surat', slug='surat', state='Gujarat')
        junk = City.objects.create(name='all world', slug='all-world')
        for i in range(3):
            _listed_agent(f'Surat {i}', f'surat-{i}', surat)
        _listed_agent('Solo', 'solo', junk)
        body = self.client.get('/about/').content.decode()
        self.assertIn('href="/insurance-agents/surat/"', body)
        self.assertNotIn('/insurance-agents/all-world/', body)

    def test_footer_renders_when_city_query_fails(self):
        from unittest import mock
        with mock.patch('apps.home.services.agent_filters.listed_agents_queryset', side_effect=RuntimeError('db down')):
            response = self.client.get('/about/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Insurance agents in:', response.content.decode())


@override_settings(ALLOWED_HOSTS=['*'])
class CalculatorDescriptionTests(TestCase):
    def setUp(self):
        from apps.home.calculators.seed import seed_calculators, seed_categories
        from apps.home.models.calculator import Calculator
        from apps.home.models.calculator_category import CalculatorCategory
        cache.clear()
        seed_categories(CalculatorCategory)
        seed_calculators(Calculator, CalculatorCategory, activate_all=True)
        self.Calculator, self.Category = Calculator, CalculatorCategory

    def _desc(self, path):
        import re
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return re.search(r'<meta name="description" content="([^"]*)"', response.content.decode()).group(1)

    def test_short_description_is_padded(self):
        calc = self.Calculator.objects.get(slug='rd-calculator')
        calc.meta_description = 'Estimate recurring deposit maturity value.'
        calc.save()
        desc = self._desc('/calculators/rd-calculator/')
        self.assertTrue(desc.startswith('Estimate recurring deposit maturity value. Free '))
        self.assertIn('verified PadosiAgent near you.', desc)

    def test_long_description_left_alone(self):
        calc = self.Calculator.objects.get(slug='rd-calculator')
        calc.meta_description = 'x' * 100
        calc.save()
        self.assertEqual(self._desc('/calculators/rd-calculator/'), 'x' * 100)
