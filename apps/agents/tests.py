from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from apps.agents.models import Agent, AgentProfile, AgentPerformanceStat, AgentReview
from django.core.cache import cache

class AgentSharingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = Agent.objects.create(
            fullname="Anil Paul Dabhi",
            email="anil.dabhi@padosiagent.com",
            mobile="9876543210",
            status="active"
        )
        self.profile = AgentProfile.objects.create(
            agent=self.agent,
            slug="anil-paul-dabhi",
            display_name="Anil Paul Dabhi",
            experience_years=12,
            license_number="IRDAI12345678",
            arn_number="AMFI987654",
            is_profile_visible=True
        )
        self.perf = AgentPerformanceStat.objects.create(
            agent=self.agent,
            claims_settled=150,
            claims_processed=160
        )

    def test_public_share_profile_view_active(self):
        response = self.client.get(reverse('agents:agent_public_share_profile', args=['anil-paul-dabhi']))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anil Paul Dabhi")
        self.assertContains(response, "IRDAI Licensed")
        self.assertContains(response, "AMFI Registered")
        self.assertContains(response, "12+ Yrs")
        self.assertContains(response, "150+")

    def test_public_share_profile_view_inactive(self):
        self.profile.is_profile_visible = False
        self.profile.save()
        
        response = self.client.get(reverse('agents:agent_public_share_profile', args=['anil-paul-dabhi']))
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, 'agents/profile_unavailable.html')
        self.assertContains(response, "Profile Not Available", status_code=404)

    def test_og_image_generator(self):
        response = self.client.get(reverse('agents:agent_og_image', args=[self.agent.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')

        # Check caching
        cache_key = f'og_image_agent_card_{self.agent.id}'
        self.assertTrue(cache.get(cache_key) is not None)

        # Check invalidation signal works
        self.profile.experience_years = 15
        self.profile.save()
        self.assertTrue(cache.get(cache_key) is None)


class AgentPublicProfileTests(TestCase):
    """
    Regression tests for the public profile page (/profile/<slug|id>/).

    Covers the production crash where guest reviews (user=NULL) caused the
    template to resolve review.user.username on None, raising
    VariableDoesNotExist / AttributeError / ValueError.
    """

    def setUp(self):
        cache.clear()
        self.agent = Agent.objects.create(
            fullname="Ravi Kumar",
            email="ravi.kumar@padosiagent.com",
            mobile="9876501234",
            status="active"
        )
        self.profile = AgentProfile.objects.create(
            agent=self.agent,
            slug="ravi-kumar",
            display_name="Ravi Kumar",
            is_profile_visible=True,
            show_reviews=True,
        )

    def test_profile_with_guest_review_null_user_renders(self):
        # Guest reviews are stored with user=None (see store_review).
        # This is the exact data shape that crashed production.
        AgentReview.objects.create(
            agent=self.agent,
            user=None,
            reviewer_name="Guest Reviewer",
            reviewer_email="guest@example.com",
            rating=5,
            review="Great service!",
            is_approved=True,
        )
        for url in (
            reverse('agents:agent_public_profile', args=['ravi-kumar']),
            reverse('agents:agent_public_profile', args=[str(self.agent.id)]),
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Guest Reviewer")

    def test_profile_with_user_review_renders(self):
        user = User.objects.create_user(
            username="client_one", email="client1@example.com", password="pw12345!"
        )
        AgentReview.objects.create(
            agent=self.agent,
            user=user,
            reviewer_name="",
            rating=4,
            review="Very professional.",
            is_approved=True,
        )
        response = self.client.get(reverse('agents:agent_public_profile', args=['ravi-kumar']))
        self.assertEqual(response.status_code, 200)
        # author_display falls back to the user's username when no name is set
        self.assertContains(response, "client_one")

    def test_missing_agent_returns_404(self):
        response = self.client.get(reverse('agents:agent_public_profile', args=['999999']))
        self.assertEqual(response.status_code, 404)

    def test_non_numeric_slug_returns_404(self):
        response = self.client.get('/profile/username/')
        self.assertEqual(response.status_code, 404)

    def test_agent_without_profile_returns_404(self):
        # An agent row with no AgentProfile must not crash the template.
        incomplete = Agent.objects.create(
            fullname="No Profile Agent",
            email="noprofile@padosiagent.com",
            mobile="9876509999",
            status="active",
        )
        response = self.client.get(reverse('agents:agent_public_profile', args=[str(incomplete.id)]))
        self.assertEqual(response.status_code, 404)

    def test_guest_review_post_does_not_404_as_state_profile(self):
        """POST /profile/<slug>/review/ must hit store_review, not profile/<state>/<slug>."""
        from django.urls import resolve
        match = resolve('/profile/ravi-kumar/review/')
        self.assertEqual(match.url_name, 'agent_store_review')
        self.assertEqual(match.kwargs.get('slug'), 'ravi-kumar')

        response = self.client.post(
            reverse('agents:agent_store_review', kwargs={'slug': 'ravi-kumar'}),
            {
                'rating': '5',
                'review': 'Very helpful and professional agent.',
                'fullname': 'Guest Reviewer',
                'email': 'guest.reviewer@example.com',
                'mobile': '9876543210',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('status'), 'success')
        self.assertTrue(
            AgentReview.objects.filter(
                agent=self.agent,
                reviewer_email='guest.reviewer@example.com',
                is_approved=True,
            ).exists()
        )
