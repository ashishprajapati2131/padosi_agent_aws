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

    def test_reviews_from_pending_approval_agent_not_displayed_on_homepage(self):
        from django.core.cache import cache
        from apps.agents.models import Agent, AgentProfile, AgentReview
        cache.delete('homepage_reviews')

        pending_agent = Agent.objects.create(
            fullname="Pending Agent",
            email="pending@example.com",
            mobile="9876543211",
            status="pending_approval",
        )
        AgentProfile.objects.create(
            agent=pending_agent,
            slug="pending-agent",
            display_name="Pending Agent",
            is_profile_visible=True,
            show_reviews=True,
        )
        AgentReview.objects.create(
            agent=pending_agent,
            reviewer_name="Customer A",
            rating=5,
            review="Excellent service from pending agent",
            is_approved=True,
        )

        response = self.client.get(reverse('home:home'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Excellent service from pending agent")
        self.assertFalse(response.context['has_reviews'])

    def test_reviews_from_active_approved_agent_displayed_on_homepage(self):
        from django.core.cache import cache
        from apps.agents.models import Agent, AgentProfile, AgentReview
        cache.delete('homepage_reviews')

        active_agent = Agent.objects.create(
            fullname="Approved Agent",
            email="approved@example.com",
            mobile="9876543212",
            status="active",
        )
        AgentProfile.objects.create(
            agent=active_agent,
            slug="approved-agent",
            display_name="Approved Agent",
            is_profile_visible=True,
            show_reviews=True,
        )
        AgentReview.objects.create(
            agent=active_agent,
            reviewer_name="Customer B",
            rating=5,
            review="Super helpful approved agent",
            is_approved=True,
        )

        response = self.client.get(reverse('home:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Super helpful approved agent")
        self.assertTrue(response.context['has_reviews'])

    def test_reviews_from_suspended_rejected_or_blacklisted_agent_not_displayed(self):
        from django.core.cache import cache
        from apps.agents.models import Agent, AgentProfile, AgentReview
        cache.delete('homepage_reviews')

        suspended_agent = Agent.objects.create(
            fullname="Suspended Agent",
            email="suspended@example.com",
            mobile="9876543213",
            status="suspended",
        )
        AgentProfile.objects.create(
            agent=suspended_agent,
            slug="suspended-agent",
            is_profile_visible=True,
            show_reviews=True,
        )
        AgentReview.objects.create(
            agent=suspended_agent,
            reviewer_name="Customer C",
            rating=5,
            review="Suspended agent review text",
            is_approved=True,
        )

        blacklisted_agent = Agent.objects.create(
            fullname="Blacklisted Agent",
            email="blacklisted@example.com",
            mobile="9876543214",
            status="active",
            is_blacklisted=True,
        )
        AgentProfile.objects.create(
            agent=blacklisted_agent,
            slug="blacklisted-agent",
            is_profile_visible=True,
            show_reviews=True,
        )
        AgentReview.objects.create(
            agent=blacklisted_agent,
            reviewer_name="Customer D",
            rating=5,
            review="Blacklisted agent review text",
            is_approved=True,
        )

        response = self.client.get(reverse('home:home'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Suspended agent review text")
        self.assertNotContains(response, "Blacklisted agent review text")
        self.assertFalse(response.context['has_reviews'])

    def test_reviews_with_hidden_profile_or_reviews_not_displayed(self):
        from django.core.cache import cache
        from apps.agents.models import Agent, AgentProfile, AgentReview
        cache.delete('homepage_reviews')

        hidden_profile_agent = Agent.objects.create(
            fullname="Hidden Agent",
            email="hidden@example.com",
            mobile="9876543215",
            status="active",
        )
        AgentProfile.objects.create(
            agent=hidden_profile_agent,
            slug="hidden-agent",
            is_profile_visible=False,
            show_reviews=True,
        )
        AgentReview.objects.create(
            agent=hidden_profile_agent,
            reviewer_name="Customer E",
            rating=5,
            review="Hidden profile review text",
            is_approved=True,
        )

        hidden_reviews_agent = Agent.objects.create(
            fullname="NoReviews Agent",
            email="noreviews@example.com",
            mobile="9876543216",
            status="active",
        )
        AgentProfile.objects.create(
            agent=hidden_reviews_agent,
            slug="noreviews-agent",
            is_profile_visible=True,
            show_reviews=False,
        )
        AgentReview.objects.create(
            agent=hidden_reviews_agent,
            reviewer_name="Customer F",
            rating=5,
            review="Hidden reviews toggle text",
            is_approved=True,
        )

        response = self.client.get(reverse('home:home'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Hidden profile review text")
        self.assertNotContains(response, "Hidden reviews toggle text")
        self.assertFalse(response.context['has_reviews'])


class StatDisplayTests(TestCase):
    def test_formats_match_js_counter(self):
        from apps.home.services.homepage import _stat_display
        self.assertEqual(_stat_display(4.8, False, True), '4.8')
        self.assertEqual(_stat_display(500.0, False, False), '500')
        self.assertEqual(_stat_display(1000.0, True, False), '1,000')
        self.assertEqual(_stat_display(1234567.0, True, False), '12,34,567')
