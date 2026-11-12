"""Anonymous reviews (no `user`) must not count toward feature unlock (audit AG2)."""
from django.contrib.auth.models import User
from django.test import TestCase

from apps.agents.models import Agent, AgentReview
from apps.agents.services.review_growth import agent_review_count


class ReviewUnlockCountsTests(TestCase):
    def test_only_logged_in_client_reviews_count(self):
        agent = Agent.objects.create(fullname='X', email='rc@example.com', mobile='9000000070', status='active')
        for i in range(5):
            AgentReview.objects.create(
                agent=agent, reviewer_name=f'Anon{i}', reviewer_mobile=f'80000000{i:02d}',
                rating=5, review='good', is_approved=True, user=None,
            )
        self.assertEqual(agent_review_count(agent), 0)

        buyer = User.objects.create_user('b@example.com', 'b@example.com', 'x')
        AgentReview.objects.create(agent=agent, user=buyer, rating=5, review='real', is_approved=True)
        self.assertEqual(agent_review_count(agent), 1)
