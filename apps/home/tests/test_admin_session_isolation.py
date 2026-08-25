from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse

from apps.admin_panel.middleware import (
    AdminPermissionMiddleware,
    IsolateAdminAgentSessionsMiddleware,
)
from apps.agents.views.dashboard import edit_profile


class AdminProfileEditorUrlTests(SimpleTestCase):
    def test_admin_full_editor_resolves_under_admin(self):
        match = resolve('/admin/agents/226/edit-profile/')
        self.assertEqual(match.url_name, 'admin_agents_edit_profile')
        self.assertEqual(match.kwargs.get('id'), 226)

    def test_admin_full_editor_update_resolves(self):
        match = resolve('/admin/agents/226/edit-profile/update/')
        self.assertEqual(match.url_name, 'admin_agents_full_update_profile')

    def test_reverse_admin_full_editor(self):
        self.assertEqual(
            reverse('admin_agents_edit_profile', kwargs={'id': 226}),
            '/admin/agents/226/edit-profile/',
        )

    def test_agent_edit_profile_stays_on_agent_path(self):
        match = resolve('/agent/edit-profile/')
        self.assertEqual(match.namespace, 'agents')
        self.assertEqual(match.url_name, 'agent_edit_profile')

    def test_agent_referral_is_not_shadowed_by_admin_urls(self):
        match = resolve('/agent/referral/')
        self.assertEqual(match.namespace, 'agents')
        self.assertEqual(match.url_name, 'agent_referral')

    def test_join_referral_uses_agent_route(self):
        match = resolve('/join/ABC123/')
        self.assertEqual(match.namespace, 'agents')
        self.assertEqual(match.url_name, 'referral_join')

    def test_agent_editor_login_required_ignores_agent_id(self):
        request = RequestFactory().get('/agent/edit-profile/', {'agent_id': '226'})
        request.user = AnonymousUser()
        response = edit_profile(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/agent-login/', response.url)


class StaffPermissionMapTests(SimpleTestCase):
    def setUp(self):
        self.middleware = AdminPermissionMiddleware(lambda request: None)

    def test_new_editor_routes_require_agents_permission(self):
        self.assertEqual(
            self.middleware.get_required_permission('admin_agents_edit_profile'),
            'agents',
        )
        self.assertEqual(
            self.middleware.get_required_permission('admin_agents_full_update_profile'),
            'agents',
        )

    def test_previously_unmapped_routes_are_gated(self):
        self.assertEqual(self.middleware.get_required_permission('admin_plans_index'), 'subscriptions')
        self.assertEqual(self.middleware.get_required_permission('admin_plan_create'), 'subscriptions')
        self.assertEqual(self.middleware.get_required_permission('admin_invoices_create'), 'invoices')
        self.assertEqual(self.middleware.get_required_permission('admin_invoices_verify_promo'), 'invoices')
        self.assertEqual(
            self.middleware.get_required_permission('admin_agents_verify_pending_payment'),
            'agents',
        )
        self.assertEqual(self.middleware.get_required_permission('admin_search'), 'dashboard')

    def test_staff_denied_from_agents_is_sent_to_their_own_module(self):
        admin = SimpleNamespace(permissions=['users'])
        self.assertEqual(self.middleware.get_first_allowed_route(admin), 'admin_users')

        admin = SimpleNamespace(permissions=['invoices'])
        self.assertEqual(self.middleware.get_first_allowed_route(admin), 'admin_invoices')

        admin = SimpleNamespace(permissions=['content'])
        self.assertEqual(self.middleware.get_first_allowed_route(admin), 'admin_content_about')

        admin = SimpleNamespace(permissions=['pending_registrations'])
        self.assertEqual(
            self.middleware.get_first_allowed_route(admin),
            'admin_agents_pending_registrations',
        )


class IsolateAdminAgentSessionsTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _middleware(self, inner=None):
        inner = inner or (lambda request: HttpResponse('ok'))
        return IsolateAdminAgentSessionsMiddleware(inner)

    def test_skips_admin_login_so_new_cookie_is_not_wiped(self):
        request = self.factory.post('/admin/login/post/')
        request.user = SimpleNamespace(is_authenticated=True, pk=9)
        request.COOKIES = {'session_token': 'old-token'}

        def login_view(req):
            response = HttpResponse('logged-in')
            response.set_cookie('session_token', 'new-token')
            return response

        with patch('apps.agents.models.Agent.objects') as mock_objects:
            response = self._middleware(login_view)(request)

        mock_objects.filter.assert_not_called()
        self.assertEqual(response.cookies['session_token'].value, 'new-token')

    @patch('apps.admin_panel.views.dashboard.invalidate_admin_session_token')
    def test_strips_admin_cookie_when_django_user_is_an_agent(self, mock_invalidate):
        request = self.factory.get('/agent/dashboard/')
        request.user = SimpleNamespace(is_authenticated=True, pk=42)
        request.COOKIES = {'session_token': 'admin-cookie'}

        mock_qs = MagicMock()
        mock_qs.exists.return_value = True

        with patch('apps.agents.models.Agent.objects') as mock_objects:
            mock_objects.filter.return_value = mock_qs
            response = self._middleware()(request)

        mock_invalidate.assert_called_once_with('admin-cookie')
        self.assertEqual(response.cookies['session_token'].value, '')
        self.assertNotIn('session_token', request.COOKIES)
