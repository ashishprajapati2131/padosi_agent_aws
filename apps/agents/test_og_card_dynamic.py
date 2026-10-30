"""The WhatsApp/OG share card shows only what the agent filled in: no placeholder numbers or badges."""
from django.test import RequestFactory, TestCase

from apps.agents.models import Agent, AgentPerformanceStat, AgentProfile, AgentReview
from apps.agents.services.og_image import _card_data, _render_agent_og_jpeg_pillow, card_version
from apps.agents.services.og_meta import profile_og_context


class OgCardDynamicTests(TestCase):
    def _agent(self, **kw):
        defaults = dict(fullname='Test Agent', email=f"a{Agent.objects.count()}@example.com",
                        mobile='9800000001', status='active')
        defaults.update(kw)
        return Agent.objects.create(**defaults)

    def test_blank_agent_shows_no_placeholders(self):
        card = _card_data(self._agent(status='pending_payment'))
        self.assertEqual(card['stats'], [])
        self.assertEqual((card['review_count'], card['rating']), (0, 0.0))
        self.assertEqual(card['location'], '')
        self.assertFalse(card['show_licensed'])
        self.assertFalse(card['show_trusted'])
        self.assertFalse(card['show_verified'])
        self.assertTrue(_render_agent_og_jpeg_pillow(self._agent()).startswith(b'\xff\xd8'))

    def test_filled_details_are_shown(self):
        agent = self._agent(client_base='1200', experience_range='8')
        AgentProfile.objects.create(agent=agent, slug='t1', license_number='IRDA1')
        AgentPerformanceStat.objects.create(agent=agent, claims_processed=340, claims_amount=25000000)
        AgentReview.objects.create(agent=agent, rating=4, is_approved=True, reviewer_name='A')
        card = _card_data(agent)
        self.assertEqual([s[1] for s in card['stats']], ['YEARS EXP', 'CLIENTS', 'CLAIMS', 'SETTLED'])
        self.assertEqual([s[0] for s in card['stats']], ['8+', '1,200+', '340+', '₹2.5Cr+'])
        self.assertEqual((card['review_count'], card['rating']), (1, 4.0))
        self.assertTrue(card['show_licensed'])

    def test_agent_privacy_toggles_hide_values(self):
        agent = self._agent(client_base='50', experience_range='5')
        AgentProfile.objects.create(agent=agent, slug='t2', show_experience=False, show_client_base=False,
                                    show_claims_stats=False, show_ratings=False)
        AgentPerformanceStat.objects.create(agent=agent, claims_processed=10, claims_amount=1000)
        AgentReview.objects.create(agent=agent, rating=5, is_approved=True, reviewer_name='A')
        card = _card_data(agent)
        self.assertEqual(card['stats'], [])
        self.assertEqual(card['review_count'], 0)

    def test_zero_values_are_hidden(self):
        agent = self._agent(client_base='0')
        AgentPerformanceStat.objects.create(agent=agent, claims_processed=0, claims_amount=0)
        self.assertEqual(_card_data(agent)['stats'], [])

    def test_image_version_changes_with_details(self):
        agent = self._agent()
        before = card_version(agent)
        Agent.objects.filter(pk=agent.pk).update(experience_range='4')
        agent.refresh_from_db()
        self.assertNotEqual(before, card_version(agent))

    def test_share_text_says_licensed_only_with_license(self):
        request = RequestFactory().get('/')
        plain = self._agent()
        AgentProfile.objects.create(agent=plain, slug='t3')
        self.assertEqual(profile_og_context(request, plain)['og_share_title'],
                         'Test Agent | Insurance & Financial Advisor')
        licensed = self._agent()
        AgentProfile.objects.create(agent=licensed, slug='t4', arn_number='ARN-1')
        self.assertEqual(profile_og_context(request, licensed)['og_share_title'],
                         'Test Agent | Licensed Insurance & Financial Advisor')
