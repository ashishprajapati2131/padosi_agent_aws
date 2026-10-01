"""Audit 2026-10-01 F-26: the free-trial "[TESTING] Add Fake Conversion" tool
inserted fake active agents and applied referral rewards on the live site."""
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from apps.agents.models import Agent


class FakeConversionToolTests(TestCase):
    def _post(self):
        from apps.admin_panel.views.free_trial import ft_force_test_credit
        target = Agent.objects.create(fullname='T', email='target@example.com', mobile='9000000131', status='active')
        request = RequestFactory().post('/admin/free-trial/force-test-credit/', {'agent_id': target.pk})
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch('apps.admin_panel.views.free_trial._get_admin_from_session', return_value=1):
            ft_force_test_credit(request)
        return target

    @override_settings(DEBUG=False)
    def test_disabled_on_the_live_site(self):
        before = Agent.objects.count()
        target = self._post()
        self.assertEqual(Agent.objects.count(), before + 1)  # only the target created above
        target.refresh_from_db()
        self.assertEqual(target.referral_reward_type, '')
