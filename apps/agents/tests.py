from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from apps.agents.models import Agent, AgentProfile, AgentPerformanceStat, AgentReview, og_image_cache_key, Client
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
        response = self.client.get(reverse('agents:agent_public_share_profile', args=['anil-paul-dabhi']), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anil Paul Dabhi")

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
        cache_key = og_image_cache_key(self.agent.id)
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

    def test_profile_og_meta_has_real_description_and_image(self):
        response = self.client.get(reverse('agents:agent_public_profile', args=['ravi-kumar']))
        body = response.content.decode()
        self.assertIn('og-image/', body)
        self.assertIn('og:image:secure_url', body)
        self.assertNotIn('&#8203;', body)
        self.assertNotIn('Digital Visiting Card', body.split('og:title')[0])  # not in head title meta
        self.assertIn('property="og:description"', body)
        self.assertIn('Connect with Ravi Kumar', body)

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

    def test_guest_review_post_with_optional_email_omitted(self):
        """Guest review without email should succeed and store reviewer_email as None."""
        response = self.client.post(
            reverse('agents:agent_store_review', kwargs={'slug': 'ravi-kumar'}),
            {
                'rating': '4',
                'review': 'Great consultation and timely advice.',
                'fullname': 'No Email Reviewer',
                'email': '',
                'mobile': '9876543222',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('status'), 'success')
        review = AgentReview.objects.filter(
            agent=self.agent,
            reviewer_mobile='9876543222',
            is_approved=True,
        ).first()
        self.assertIsNotNone(review)
        self.assertIsNone(review.reviewer_email)
        self.assertEqual(review.reviewer_name, 'No Email Reviewer')

    def test_guest_review_duplicate_mobile_rejected(self):
        """Duplicate review from the same mobile number for the same agent should be rejected with 422."""
        AgentReview.objects.create(
            agent=self.agent,
            reviewer_name='Prior Reviewer',
            reviewer_mobile='9876543333',
            rating=5,
            review='First review from this number.',
            is_approved=True,
        )
        response = self.client.post(
            reverse('agents:agent_store_review', kwargs={'slug': 'ravi-kumar'}),
            {
                'rating': '5',
                'review': 'Second review attempt with same mobile.',
                'fullname': 'Another Person',
                'email': 'different@example.com',
                'mobile': '9876543333',
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn('mobile', response.json().get('errors', {}))

    def test_public_review_page_renders_form_with_popup(self):
        """GET /review/<slug>/ renders clean review form and guest popup details fields."""
        response = self.client.get(
            reverse('agents:agent_public_review', kwargs={'slug': 'ravi-kumar'})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="paRating"')
        self.assertContains(response, 'id="paReviewText"')
        self.assertContains(response, 'swal-fullname')
        self.assertContains(response, 'swal-email')
        self.assertContains(response, 'swal-mobile')


class AchievementPhotoUrlTests(SimpleTestCase):
    def test_laravel_path_resolves_to_uploaded_django_folder(self):
        import os
        from apps.agents.models import AgentAchievementPhoto, resolve_stored_file_url

        with self.settings(MEDIA_ROOT=self._media_root()):
            dest_dir = os.path.join(self._tmp, 'app', 'public', 'achievement')
            os.makedirs(dest_dir, exist_ok=True)
            filename = 'HASHFILE123.jpg'
            with open(os.path.join(dest_dir, filename), 'wb') as fh:
                fh.write(b'fake-image')

            url = resolve_stored_file_url(
                f'agent/achievements/{filename}',
                fallback_subdirs=('app/public/achievement', 'agent/achievements'),
            )
            self.assertEqual(url, f'/media/app/public/achievement/{filename}')

            photo = AgentAchievementPhoto(photo_path=f'agent/achievements/{filename}')
            self.assertEqual(photo.photo_url, f'/media/app/public/achievement/{filename}')

    def _media_root(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        return self._tmp


class ClientQuickRegisterTests(TestCase):
    def test_quick_register_new_client(self):
        import json
        payload = {
            'fullname': 'Mehul Shah',
            'mobile': '9876543210',
            'email': '9876543210@padosiagent.com',
            'pincode': '380015'
        }
        response = self.client.post(
            reverse('agents:client_quick_register'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))

        # Verify user created and logged in
        user = User.objects.filter(email='9876543210@padosiagent.com').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.first_name, 'Mehul')
        self.assertEqual(user.last_name, 'Shah')

        # Verify client record
        client_rec = Client.objects.filter(user=user).first()
        self.assertIsNotNone(client_rec)
        self.assertEqual(client_rec.mobile, '9876543210')

        # Verify session
        session = self.client.session
        self.assertIn('quick_lead_user', session)
        self.assertEqual(session['quick_lead_user']['mobile'], '9876543210')

    def test_quick_register_existing_client(self):
        import json
        user = User.objects.create_user(
            username='existinguser',
            email='existing@example.com',
            first_name='Existing',
            last_name='Client'
        )
        Client.objects.create(user=user, mobile='9876543211', pincode='380015')

        payload = {
            'fullname': 'Existing Client',
            'mobile': '9876543211',
            'email': '9876543211@padosiagent.com'
        }
        response = self.client.post(
            reverse('agents:client_quick_register'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertIn('Welcome back', data.get('message'))

    def test_quick_register_validation_errors(self):
        import json
        payload = {
            'fullname': '',
            'mobile': '123'
        }
        response = self.client.post(
            reverse('agents:client_quick_register'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn('fullname', data.get('errors', {}))
        self.assertIn('mobile', data.get('errors', {}))

    def test_quick_register_then_lead_capture(self):
        import json
        from apps.agents.models import Agent, AgentProfile, AgentLead
        # Create an agent to contact
        agent = Agent.objects.create(
            fullname="Test Agent",
            email="testagent@padosiagent.com",
            mobile="9876543299",
            status="active"
        )
        AgentProfile.objects.create(
            agent=agent,
            whatsapp="9876543299",
            display_name="Test Agent"
        )

        # 1. Quick register as guest
        reg_payload = {
            'fullname': 'Happy Client',
            'mobile': '9876543288',
            'email': '9876543288@padosiagent.com',
            'pincode': '380015'
        }
        reg_resp = self.client.post(
            reverse('agents:client_quick_register'),
            data=json.dumps(reg_payload),
            content_type='application/json'
        )
        self.assertEqual(reg_resp.status_code, 200)

        # 2. Subsequent contact click (e.g. WhatsApp) without re-prompting popup
        lead_payload = {
            'agent_id': agent.id,
            'interaction_type': 'whatsapp',
            'service_type': 'Buy New Insurance',
            'insurance_type': 'Health',
            'source_page': '/find-agents/'
        }
        lead_resp = self.client.post(
            reverse('agents:agent_leads_capture'),
            data=lead_payload
        )
        self.assertEqual(lead_resp.status_code, 200)
        lead_data = lead_resp.json()
        self.assertTrue('whatsapp' in lead_data.get('url', '') or 'wa.me' in lead_data.get('url', ''))

        # Verify lead created with customer details from session/user
        lead = AgentLead.objects.filter(agent=agent).first()
        self.assertIsNotNone(lead)
        self.assertEqual(lead.customer_mobile, '9876543288')
        self.assertEqual(lead.customer_name, 'Happy Client')


class ProfileBannerFeatureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='banneragent',
            email='banner@test.com',
            password='password123'
        )
        self.agent = Agent.objects.create(
            user=self.user,
            fullname='Banner Hero',
            email='banner@test.com',
            mobile='9876543210',
            status='active'
        )
        self.profile = AgentProfile.objects.create(
            agent=self.agent,
            slug='banner-hero',
            display_name='Banner Hero',
            languages='English, Gujarati',
            address='123 Ashram Road'
        )
        from apps.home.models.site_setting import SiteSetting
        SiteSetting.set_value('profile_banner_enabled', '1')
        SiteSetting.set_value('profile_banner_allow_custom_upload', '1')

        from apps.agents.models import ProfileBannerPreset
        self.preset = ProfileBannerPreset.objects.create(
            title='Executive Shield Test',
            category='Corporate',
            image_path='banners/presets/preset_1_executive_navy.svg',
            display_order=1,
            is_active=True
        )

    def test_preset_model_and_image_url(self):
        self.assertEqual(self.preset.title, 'Executive Shield Test')
        self.assertTrue(self.preset.image_url.startswith('/media/'))
        self.assertIn('preset_1_executive_navy.svg', self.preset.image_url)

    def test_banner_image_url_with_preset(self):
        self.profile.banner_preset = self.preset
        self.profile.custom_banner_path = None
        self.profile.save()

        self.assertEqual(self.profile.banner_image_url, self.preset.image_url)

    def test_banner_image_url_with_custom_banner(self):
        self.profile.banner_preset = self.preset
        self.profile.custom_banner_path = 'banners/custom/my_custom_banner.png'
        self.profile.save()

        # Custom banner overrides preset when allowed
        self.assertEqual(self.profile.banner_image_url, '/media/banners/custom/my_custom_banner.png')

    def test_feature_flag_master_disable(self):
        from apps.home.models.site_setting import SiteSetting
        self.profile.banner_preset = self.preset
        self.profile.save()

        SiteSetting.set_value('profile_banner_enabled', '0')
        self.assertIsNone(self.profile.banner_image_url)

    def test_apply_profile_update_preset_selection(self):
        from apps.agents.views.dashboard import apply_profile_update
        from django.test.client import RequestFactory

        factory = RequestFactory()
        request = factory.post('/agent/update-profile/', {
            'current_step': '1',
            'full_name': 'Banner Hero Updated',
            'mobile': '9876543210',
            'languages': 'English',
            'address': 'New Address 456',
            'banner_preset_id': str(self.preset.id),
        })
        request.user = self.user

        response = apply_profile_update(request, self.agent, is_admin_edit=False)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.banner_preset_id, self.preset.id)
        self.assertIsNone(self.profile.custom_banner_path)

    def test_apply_profile_update_remove_banner(self):
        from apps.agents.views.dashboard import apply_profile_update
        from django.test.client import RequestFactory

        self.profile.banner_preset = self.preset
        self.profile.custom_banner_path = 'banners/custom/old.jpg'
        self.profile.save()

        factory = RequestFactory()
        request = factory.post('/agent/update-profile/', {
            'current_step': '1',
            'full_name': 'Banner Hero',
            'mobile': '9876543210',
            'languages': 'English',
            'address': 'New Address 456',
            'remove_banner': '1',
        })
        request.user = self.user

        apply_profile_update(request, self.agent, is_admin_edit=False)
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.banner_preset)
        self.assertIsNone(self.profile.custom_banner_path)

    def test_public_profile_renders_banner_image(self):
        self.profile.banner_preset = self.preset
        self.profile.save()

        response = self.client.get(
            reverse('agents:agent_public_profile', kwargs={'slug': 'banner-hero'})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'has-custom-banner')
        self.assertContains(response, self.preset.image_url)



