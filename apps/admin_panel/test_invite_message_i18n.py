"""Distributor invite message translations are whitelisted, cleaned and stored."""
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from apps.admin_panel.views import settings as s
from apps.home.models.site_setting import SiteSetting


class InviteMessageI18nTests(TestCase):
    def test_save_cleans_translations(self):
        request = RequestFactory().post('/x/', {
            'group': 'general',
            'distributor_invite_message': 'Join {LINK}',
            'distributor_invite_message_i18n': '{"gu": "જોડાઓ {LINK}", "zz": "bad"}',
        })
        request.session = {}
        from django.contrib.messages.storage.fallback import FallbackStorage
        request._messages = FallbackStorage(request)
        with patch.object(s, '_get_admin_from_session', return_value=1), \
                patch.object(s, 'AdminActivityLog', create=True):
            s.update_settings(request)
        self.assertEqual(SiteSetting.get_value('distributor_invite_message_i18n'), {'gu': 'જોડાઓ {LINK}'})
        self.assertEqual(SiteSetting.get_value('distributor_invite_message'), 'Join {LINK}')
