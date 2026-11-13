"""Admin Activate / Deactivate must block sign-in and every public surface."""
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from fastapi import HTTPException

from apps.agents.models import Agent, AgentProfile, AgentSubscription
from apps.agents.services.agent_access import (
    RESTRICTED_LOGIN_MESSAGE,
    activate_agent,
    deactivate_agent,
)
from apps.home.services.agent_filters import listed_agents_queryset
from password_hashing import hash_password


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class AdminRestrictionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'restricted.agent@example.com',
            'restricted.agent@example.com',
            None,
        )
        self.user.password = hash_password('9000001801')
        self.user.save(update_fields=['password'])
        self.agent = Agent.objects.create(
            user=self.user,
            fullname='Restricted Agent',
            email='restricted.agent@example.com',
            mobile='9000001801',
            status='active',
            plan_type='starter',
        )
        AgentProfile.objects.create(
            agent=self.agent,
            slug='restricted-agent',
            is_profile_visible=True,
            is_card_visible=True,
        )

    def test_deactivate_blocks_web_login_with_the_contact_message(self):
        deactivate_agent(self.agent)
        response = self.client.post('/agent-login/', {
            'email': 'restricted.agent@example.com',
            'password': '9000001801',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, RESTRICTED_LOGIN_MESSAGE)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, 'suspended')
        self.assertTrue(self.agent.admin_restricted)

    def test_open_session_is_logged_out_on_the_next_portal_request(self):
        self.client.force_login(self.user)
        deactivate_agent(self.agent)
        response = self.client.get('/agent/dashboard/', follow=True)
        self.assertContains(response, RESTRICTED_LOGIN_MESSAGE)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(response.request['PATH_INFO'], '/agent-login/')

    def test_public_surfaces_hide_a_restricted_agent(self):
        visible = Agent.objects.create(
            fullname='Visible Agent',
            email='visible.agent@example.com',
            mobile='9000001802',
            status='active',
        )
        self.assertIn(self.agent.pk, listed_agents_queryset().values_list('pk', flat=True))
        deactivate_agent(self.agent)
        listed_ids = set(listed_agents_queryset().values_list('pk', flat=True))
        self.assertNotIn(self.agent.pk, listed_ids)
        self.assertIn(visible.pk, listed_ids)

        profile = self.client.get('/profile/restricted-agent/')
        self.assertEqual(profile.status_code, 404)
        self.assertContains(profile, 'Profile Not Available', status_code=404)

        card = self.client.get(reverse('agents:agent_public_card', kwargs={'slug': 'restricted-agent'}))
        self.assertEqual(card.status_code, 404)

        review = self.client.post(
            reverse('agents:agent_store_review', kwargs={'slug': 'restricted-agent'}),
            {'rating': '5', 'review': 'Great'},
        )
        self.assertEqual(review.status_code, 404)

        lead = self.client.post('/agent/leads/capture/', {
            'agent_id': self.agent.pk,
            'interaction_type': 'call',
        })
        self.assertEqual(lead.status_code, 404)

    def test_activate_restores_the_previous_status_and_listing(self):
        self.agent.status = 'pending_approval'
        self.agent.save(update_fields=['status'])
        deactivate_agent(self.agent)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status_before_restriction, 'pending_approval')
        restored = activate_agent(self.agent)
        self.agent.refresh_from_db()
        self.assertEqual(restored, 'pending_approval')
        self.assertFalse(self.agent.admin_restricted)
        self.assertNotIn(self.agent.pk, listed_agents_queryset().values_list('pk', flat=True))

        self.agent.status = 'active'
        self.agent.save(update_fields=['status'])
        self.assertIn(self.agent.pk, listed_agents_queryset().values_list('pk', flat=True))

    def test_captured_payment_does_not_clear_the_restriction(self):
        from apps.agents.views.registration import _activate_paid_subscription

        deactivate_agent(self.agent)
        sub = AgentSubscription.objects.create(
            agent=self.agent,
            selected_plan="Starter's Plan",
            registration_amount=Decimal('1999.00'),
            payment_status='pending',
            status='inactive',
            razorpay_order_id='order_RESTRICT0001',
        )
        _activate_paid_subscription(
            self.agent,
            sub,
            {'id': 'pay_RESTRICT0001', 'signature': 'sig'},
            queue_fulfilment=False,
        )
        self.agent.refresh_from_db()
        sub.refresh_from_db()
        self.assertTrue(self.agent.admin_restricted)
        self.assertEqual(self.agent.status, 'suspended')
        self.assertEqual(sub.payment_status, 'completed')

    def test_inactive_payload_is_stored_as_a_real_restriction(self):
        from apps.admin_panel.views.agents import toggle_status

        request = RequestFactory().post(
            '/admin/agents/toggle-status/',
            data=json.dumps({'id': self.agent.pk, 'status': 'inactive'}),
            content_type='application/json',
        )
        request.session = {}
        request.admin_user = SimpleNamespace(role='staff', permissions=['agents'])
        with patch('apps.admin_panel.views.agents._get_admin_from_session', return_value=1):
            response = toggle_status(request)
        self.assertEqual(response.status_code, 200)
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.admin_restricted)
        self.assertEqual(self.agent.status, 'suspended')
        self.assertEqual(self.agent.status_before_restriction, 'active')

    def test_api_login_and_token_reject_a_restricted_agent(self):
        from fastapi_app.dependencies.auth import get_current_agent
        from fastapi_app.schemas.auth import LoginRequest
        from fastapi_app.services.auth_service import AuthService

        deactivate_agent(self.agent)
        agent = SimpleNamespace(
            id=self.agent.pk,
            email=self.agent.email,
            status='suspended',
            admin_restricted=True,
            fullname=self.agent.fullname,
        )
        user = SimpleNamespace(
            id=4,
            email=self.agent.email,
            password=self.user.password,
            role='agent',
            status='active',
            fullname=self.agent.fullname,
            last_login_at=None,
        )
        service = AuthService(MagicMock(), MagicMock(), MagicMock())
        service.user_repo.get_by_email.return_value = user
        service.agent_repo.get_by_email.return_value = agent
        with patch('fastapi_app.utils.client_ip.get_client_ip', return_value='127.0.0.1'), \
                patch('fastapi_app.services.auth_service.check_login_throttle', return_value=True), \
                patch('fastapi_app.services.auth_service.account_login_allowed', return_value=True):
            body = service.login(
                LoginRequest(email=self.agent.email, password='9000001801'),
                SimpleNamespace(),
            )
        payload = json.loads(body.body)
        self.assertFalse(payload['success'])
        self.assertEqual(payload['message'], RESTRICTED_LOGIN_MESSAGE)

        with patch('fastapi_app.dependencies.auth.AgentRepository') as repo:
            repo.return_value.get_by_email.return_value = agent
            with self.assertRaises(HTTPException) as ctx:
                get_current_agent(
                    current_user=SimpleNamespace(id=4, email=self.agent.email, status='active'),
                    db=MagicMock(),
                )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, RESTRICTED_LOGIN_MESSAGE)
