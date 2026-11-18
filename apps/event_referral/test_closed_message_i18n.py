"""closed_message translations are saved cleaned and shown per visitor language."""
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import Client, RequestFactory, TestCase, override_settings

from apps.event_referral.models import EventReferralCampaign
from apps.event_referral.views import admin_views


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class ClosedMessageI18nTests(TestCase):
    def tearDown(self):
        from django.core.cache import cache
        cache.clear()  # campaign is cached; the test DB row is rolled back

    def setUp(self):
        EventReferralCampaign.objects.all().delete()
        self.campaign = EventReferralCampaign.objects.create(is_enabled=False)

    def test_admin_save_cleans_translations(self):
        request = RequestFactory().post('/x/', {
            'closed_message': 'Closed for now',
            'closed_message_i18n': '{"hi": "abhi band hai", "xx": "bad"}',
        })
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch('apps.event_referral.views.admin_views._get_admin_from_session', return_value=1):
            admin_views.admin_update_settings(request)
        c = EventReferralCampaign.objects.get(pk=self.campaign.pk)
        self.assertEqual(c.closed_message, 'Closed for now')
        self.assertEqual(c.closed_message_i18n, {'hi': 'abhi band hai'})

    def test_public_page_uses_visitor_language(self):
        self.campaign.closed_message = 'Closed for now'
        self.campaign.closed_message_i18n = {'hi': 'abhi band hai'}
        self.campaign.save()
        with patch.object(EventReferralCampaign, 'get_current', return_value=self.campaign):
            client = Client()
            client.cookies['padosi_lang'] = 'hi'
            self.assertContains(client.get('/48HR/'), 'abhi band hai')
            client.cookies['padosi_lang'] = 'en'
            self.assertContains(client.get('/48HR/'), 'Closed for now')
