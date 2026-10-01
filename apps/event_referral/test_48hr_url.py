"""The Paldi page lives at /48HR/; the old /event-registration/ address and
lowercase /48hr/ redirect there, keeping sub-path and query string."""
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.event_referral.models import EventReferralCampaign


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class PaldiUrlTests(TestCase):
    def setUp(self):
        EventReferralCampaign.objects.all().delete()
        EventReferralCampaign.objects.create(is_enabled=True)

    def test_new_addresses(self):
        self.assertEqual(reverse('event_referral:register'), '/48HR/')
        self.assertEqual(reverse('event_referral:public_leaderboard'), '/48HR/leaderboard/')
        page = Client().get('/48HR/')
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context['event_referral_mode'])
        self.assertEqual(Client().get('/48HR/leaderboard/').status_code, 200)

    def test_old_and_lowercase_addresses_redirect(self):
        cases = {
            '/event-registration/': '/48HR/',
            '/event-registration/leaderboard/': '/48HR/leaderboard/',
            '/event-registration/?utm_source=wa': '/48HR/?utm_source=wa',
            '/48hr/': '/48HR/',
            '/48hr/leaderboard/': '/48HR/leaderboard/',
        }
        for old, new in cases.items():
            with self.subTest(old=old):
                r = Client().get(old)
                self.assertEqual(r.status_code, 302)
                self.assertEqual(r['Location'], new)

    def test_old_link_still_opens_the_page(self):
        r = Client().get('/event-registration/', follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context['event_referral_mode'])
        self.assertTrue(Client().session is not None)

    def test_admin_shows_the_new_public_link(self):
        from unittest.mock import patch
        from django.test import RequestFactory
        from apps.event_referral.views.admin_views import admin_dashboard
        request = RequestFactory().get('/admin/event-referral/')
        request.session = {}
        with patch('apps.event_referral.views.admin_views._get_admin_from_session', return_value=1), \
             patch('apps.admin_panel.context_processors.admin_badge_counts', return_value={}):
            html = admin_dashboard(request).content.decode()
        self.assertIn('/48HR/', html)
        self.assertNotIn('/event-registration/', html)
