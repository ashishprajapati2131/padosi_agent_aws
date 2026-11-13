"""Section 3 (agent dashboard / profile / public) follow-ups: AG5, AG17, AG18, AG19."""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.agents.models import Agent, AgentProfile, AgentSubscription


class RejectedProfileSaveWritesNothingTests(TestCase):  # AG5
    def test_full_save_with_bad_url_keeps_old_name(self):
        cache.clear()
        user = User.objects.create_user('ag5', 'ag5@example.com', 'pw12345!')
        agent = Agent.objects.create(user=user, fullname='Old Name', email='ag5@example.com',
                                     mobile='9876500901', status='active', plan_type='starter',
                                     experience_range='2')
        AgentProfile.objects.create(agent=agent, slug='ag5', languages='Gujarati', address='Ahmedabad')
        agent.insuranceSegments.create(segment_type='life')
        AgentSubscription.objects.create(agent=agent, selected_plan="Starter's Plan",
                                         registration_amount=1999, payment_status='completed',
                                         status='active', razorpay_order_id='order_AG5TEST00001',
                                         razorpay_payment_id='pay_AG5TEST00001')
        self.client.force_login(user)
        # Step 1 passes (new name) but a later step fails validation in the same full save.
        r = self.client.post(reverse('agents:agent_update_profile'), {
            'full_name': 'New Name', 'mobile': '9876500901', 'address': 'Ahmedabad',
            'languages': 'Gujarati', 'website': 'javascript:alert(1)',
            'linkedin': 'javascript:alert(1)',
        })
        self.assertIn(r.status_code, (400, 422), r.content)
        agent.refresh_from_db()
        self.assertEqual(agent.fullname, 'Old Name')


class ReviewRateLimitTests(TestCase):  # AG17
    def test_twenty_first_review_from_one_ip_is_refused(self):
        cache.clear()
        agent = Agent.objects.create(fullname='R', email='rl@example.com', mobile='9876500902', status='active')
        AgentProfile.objects.create(agent=agent, slug='rl-agent')
        url = reverse('agents:agent_store_review', args=['rl-agent'])
        codes = [self.client.post(url, {'rating': 5, 'review': 'x', 'fullname': f'N{i}',
                                        'mobile': f'98765{i:05d}'}).status_code for i in range(21)]
        self.assertNotIn(429, codes[:20])
        self.assertEqual(codes[20], 429)


class SlugRaceTests(TestCase):  # AG18
    def test_insert_collision_retries_with_random_suffix(self):
        from django.db.models.query import QuerySet

        a1 = Agent.objects.create(fullname='Same Name', email='s1@example.com', mobile='9876500903')
        a2 = Agent.objects.create(fullname='Same Name', email='s2@example.com', mobile='9876500904')
        AgentProfile.objects.create(agent=a1, slug='same-name')

        real_exists = QuerySet.exists
        calls = {'n': 0}

        def racy_exists(qs):
            # First uniqueness check misses the row another signup just inserted.
            calls['n'] += 1
            return False if calls['n'] == 1 else real_exists(qs)

        with patch.object(QuerySet, 'exists', racy_exists):
            p2 = AgentProfile(agent=a2, display_name='Same Name')
            p2.save()

        p2.refresh_from_db()
        self.assertTrue(p2.slug.startswith('same-name-'))
        self.assertEqual(AgentProfile.objects.filter(slug='same-name').count(), 1)


class ThreadConnectionCleanupTests(TestCase):  # AG19
    def test_wrapper_closes_connections_after_the_call(self):
        from apps.agents.views.dashboard import _with_fresh_db

        with patch('django.db.close_old_connections') as close:
            self.assertEqual(_with_fresh_db(lambda x: x + 1)(1), 2)
        close.assert_called_once()
