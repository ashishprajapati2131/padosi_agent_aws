from django.test import TestCase
from django.urls import reverse
from apps.home.models.site_setting import SiteSetting


class HomePageTests(TestCase):
    def test_home_page_status_code(self):
        response = self.client.get(reverse('home:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PadosiAgent")

    def test_home_page_custom_settings(self):
        custom_hero = {
            'heading': 'Our {Trusted} Team in your {Padosi}'
        }
        SiteSetting.set_value('hero_section', custom_hero, 'homepage')
        response = self.client.get(reverse('home:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Our <span class="pa-heading-trusted">Trusted</span> Team')

    def test_home_page_renders_cms_sections(self):
        SiteSetting.set_value('hero_section', {
            'heading': 'Find a {Trusted} Insurance Expert in your {Padosi}',
            'trust_badges': [{'icon': 'check-circle', 'label': 'Licensed Experts'}],
            'stats': [{'label': 'Expert Agents', 'target': 1000, 'suffix': '+', 'icon': 'users', 'large': True, 'decimal': False}],
            'tiles': [{'label': 'Health Insurance', 'icon': 'heart', 'url': '/find-agents/', 'tileClass': 'pa-tile-rose'}],
        }, 'homepage')
        SiteSetting.set_value('homepage_content', {
            'dyk': {
                'visible': True,
                'slides': [{
                    'accent': 'accent-rose',
                    'bg': 'bg-rose-500',
                    'icon': 'users',
                    'title': '3× faster claim settlements',
                    'body': 'Nearby agents help claims clear faster.',
                }],
            },
            'quickpicks': {
                'visible': True,
                'items': [{'label': 'Mediclaim', 'badge': 'Most Bought', 'icon': 'heart-pulse', 'url': '/find-agents/'}],
            },
            'why_choose': {
                'visible': True,
                'cards': [{
                    'stat': '0',
                    'caption': 'Spam Calls',
                    'icon': 'shield-check',
                    'title': 'Privacy-first by design',
                    'body': 'Only you can contact an agent.',
                }],
            },
            'works': {
                'visible': True,
                'steps': [{'icon': 'search', 'accent': 'accent-primary', 'badge': '1', 'title': 'Search', 'desc': 'Find verified agents'}],
            },
        }, 'homepage')

        response = self.client.get(reverse('home:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Licensed Experts')
        self.assertContains(response, 'Health Insurance')
        self.assertContains(response, 'Expert Agents')
        self.assertContains(response, '3× faster claim settlements')
        self.assertContains(response, 'Mediclaim')
        self.assertContains(response, 'Privacy-first by design')
        self.assertContains(response, 'Find verified agents')

    def test_home_page_falls_back_to_defaults_when_cms_empty(self):
        response = self.client.get(reverse('home:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Licensed')
        self.assertContains(response, 'Health Insurance')
        self.assertContains(response, 'Mediclaim')
        self.assertContains(response, 'Find verified agents')

    def test_home_has_no_placeholder_reviews_and_has_org_schema(self):
        from django.core.cache import cache
        cache.delete('homepage_reviews')
        response = self.client.get(reverse('home:home'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Rahul Verma')
        self.assertNotContains(response, 'id="review-slider"')
        self.assertContains(response, '"@type": "Organization"')
        self.assertContains(response, '"@type": "WebSite"')

    def test_hero_stats_render_real_values_not_zero(self):
        # Crawlers and no-JS visitors must see the counter's final value.
        response = self.client.get(reverse('home:home'))
        self.assertContains(response, 'id="pa-counter-0">1,000</span>')
        self.assertNotContains(response, 'id="pa-counter-0">0</span>')


class StatDisplayTests(TestCase):
    def test_formats_match_js_counter(self):
        from apps.home.services.homepage import _stat_display
        self.assertEqual(_stat_display(4.8, False, True), '4.8')
        self.assertEqual(_stat_display(500.0, False, False), '500')
        self.assertEqual(_stat_display(1000.0, True, False), '1,000')
        self.assertEqual(_stat_display(1234567.0, True, False), '12,34,567')
