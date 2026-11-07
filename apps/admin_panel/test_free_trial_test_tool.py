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


class FreeTrialIndexEmptyTests(TestCase):
    """Audit 2026-11-07: with no trial_ends_at rows, a function-local `import settings`
    left `settings` unbound and the page crashed with UnboundLocalError."""

    def test_index_renders_with_no_trial_rows(self):
        from contextlib import ExitStack

        from apps.admin_panel.views import free_trial

        request = RequestFactory().get("/admin/free-trial/")
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        # The raw SQL is MySQL-specific; feed the view empty data (its own logic is what broke).
        stubs = {
            "_get_admin_from_session": 1,
            "count_free_trial_history": 0,
            "fetch_trial_stats": {},
            "fetch_trial_promo_codes": [],
            "fetch_trial_agents": [],
            "fetch_monthly_stats": [],
            "fetch_promo_usage_summary": [],
            "fetch_trial_history": [],
        }
        with ExitStack() as stack:
            for name, value in stubs.items():
                stack.enter_context(patch.object(free_trial, name, return_value=value))
            stack.enter_context(patch.object(free_trial, "render", side_effect=lambda req, tpl, ctx: ctx))
            ctx = free_trial.free_trial_index(request)
        self.assertIn("show_test_tools", ctx)
