"""Audit 2026-10-01 F-07: `agents.user_id` holds the Django auth_user id, but
several places used it as a Laravel `users.id`, so they read or wrote a
different person's `users` row (mobile password change, insurance approve /
reject)."""
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User as AuthUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.admin_panel.models.users import User as LaravelUser
from apps.agents.models import Agent
from password_hashing import check_password_hash, hash_password


class MobilePasswordChangeTargetsOwnRowTests(TestCase):
    def test_in_app_change_updates_the_agents_own_users_row(self):
        from fastapi_app.schemas.auth import ResetPasswordRequest
        from fastapi_app.services.password_reset_service import PasswordResetService

        own = MagicMock(email='me@example.com', password=hash_password('Old@Pass123'))
        stranger = MagicMock(email='stranger@example.com', password=hash_password('Theirs@123'))
        stranger_hash = stranger.password
        service = PasswordResetService(MagicMock())
        service.user_repo = MagicMock()
        service.user_repo.get_by_email.side_effect = lambda e: own if e == 'me@example.com' else None
        agent = MagicMock(email='me@example.com', user=stranger)  # relation points at users.id == auth_user.id

        resp = service.reset_password(
            ResetPasswordRequest(password='New@Pass1234', password_confirmation='New@Pass1234'),
            None, current_agent=agent,
        )
        self.assertEqual(resp.status_code, 200, resp.body)
        self.assertTrue(check_password_hash('New@Pass1234', own.password))
        self.assertEqual(stranger.password, stranger_hash)


class InsuranceApprovalUsesAgentEmailTests(TestCase):
    def setUp(self):
        self.auth_user = AuthUser.objects.create_user('ins.agent', 'ins.agent@example.com', 'x')
        # A different person's `users` row whose id equals the agent's auth_user id.
        self.stranger = LaravelUser.objects.create(
            id=self.auth_user.id, fullname='Stranger', email='stranger@example.com',
            password='$2y$10$x', role='agent', status='active')
        self.own = LaravelUser.objects.create(
            fullname='Ins Agent', email='ins.agent@example.com',
            password='$2y$10$x', role='agent', status='inactive')
        self.agent = Agent.objects.create(user=self.auth_user, fullname='Ins Agent', email='ins.agent@example.com',
                                          mobile='9000000031', status='pending_admin_approval')

    def _post(self, view, **data):
        request = RequestFactory().post('/admin/insurance-approvals/x/', data)
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch('apps.admin_panel.views.insurance_approvals._get_admin_from_session', return_value=1):
            return view(request, self.agent.pk)

    def test_reject_deactivates_only_the_agents_own_row(self):
        from apps.admin_panel.views.insurance_approvals import insurance_approvals_reject_onboarding
        self.own.status = 'active'
        self.own.save()
        self._post(insurance_approvals_reject_onboarding, admin_note='Documents missing')
        self.stranger.refresh_from_db()
        self.own.refresh_from_db()
        self.assertEqual((self.stranger.status, self.own.status), ('active', 'inactive'))

    def test_approve_activates_only_the_agents_own_row(self):
        from apps.admin_panel.views.insurance_approvals import insurance_approvals_approve_onboarding
        self.stranger.status = 'inactive'
        self.stranger.save()
        with patch('apps.admin_panel.views.insurance_approvals.ReferralCode'):
            self._post(insurance_approvals_approve_onboarding)
        self.stranger.refresh_from_db()
        self.own.refresh_from_db()
        self.assertEqual((self.stranger.status, self.own.status), ('inactive', 'active'))
