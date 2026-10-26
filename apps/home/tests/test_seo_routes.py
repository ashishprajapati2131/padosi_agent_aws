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
