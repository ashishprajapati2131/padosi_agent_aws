"""Whole-account restrict switch: login message, and no public agent surfaces."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.agents.models import Agent, AgentProfile, AgentSubscription
from apps.agents.services.account_auth import ACCOUNT_RESTRICTED_MESSAGE
from apps.home.models import SiteSetting
from apps.home.services.agent_filters import listed_agents_queryset


class ToggleAccountTests(TestCase):
    def setUp(self):
        self.agent = Agent.objects.create(
            fullname='Toggle Agent',
            email='toggle-account@example.com',
            mobile='9000008111',
            status='active',
        )
        AgentProfile.objects.create(
            agent=self.agent,
            slug='toggle-account-agent',
            display_name='Toggle Agent',
            is_card_visible=True,
            is_profile_visible=True,
        )

    def _toggle(self, active, perms=None, role='staff'):
        from apps.admin_panel.views.agents import toggle_account
        request = RequestFactory().post(
            '/admin/agents/toggle-account/',
            data=json.dumps({'id': self.agent.pk, 'active': active}),
            content_type='application/json',
        )
        request.session = {}
        request.admin_user = SimpleNamespace(
            role=role,
            permissions=perms if perms is not None else ['agents'],
        )
        with patch('apps.admin_panel.views.agents._get_admin_from_session', return_value=1):
            response = toggle_account(request)
        self.agent.refresh_from_db()
        self.agent.profile.refresh_from_db()
        return response.status_code, json.loads(response.content)

    def test_restrict_and_restore_leave_status_and_card_visibility(self):
        code, body = self._toggle(False)
        self.assertEqual(code, 200)
        self.assertTrue(body['success'])
        self.assertFalse(self.agent.is_account_active)
        self.assertEqual(self.agent.status, 'active')
        self.assertTrue(self.agent.profile.is_card_visible)

        code, body = self._toggle(True)
        self.assertEqual(code, 200)
        self.assertTrue(body['is_account_active'])
        self.assertTrue(self.agent.is_account_active)
        self.assertEqual(self.agent.status, 'active')
        self.assertTrue(self.agent.profile.is_card_visible)

    def test_approvals_only_staff_cannot_restrict(self):
        code, body = self._toggle(False, perms=['approvals_awaiting_verification'])
        self.assertEqual(code, 403)
        self.assertFalse(body['success'])
        self.assertTrue(self.agent.is_account_active)


class RestrictedLoginTests(TestCase):
    def setUp(self):
        self.email = 'restricted.login@example.com'
        self.agent = Agent.objects.create(
            fullname='Restricted Login',
            email=self.email,
            mobile='9000008112',
            status='active',
            is_account_active=False,
        )

    @patch('apps.agents.views.auth.login')
    @patch('apps.agents.views.auth.verify_agent_password')
    @patch('apps.agents.views.auth.find_agent')
    def test_password_login_shows_restriction_message(self, mock_find, mock_verify, mock_login):
        mock_find.return_value = self.agent
        mock_verify.return_value = (True, None, SimpleNamespace(email=self.email))
        response = self.client.post(reverse('agents:agent_login'), {
            'email': self.email,
            'password': 'whatever-pass',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ACCOUNT_RESTRICTED_MESSAGE)
        mock_login.assert_not_called()

    @patch('apps.agents.views.auth.find_agent')
    @patch('requests.get')
    @patch('requests.post')
    def test_google_callback_shows_restriction_message(self, mock_post, mock_get, mock_find):
        mock_find.return_value = self.agent
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {'access_token': 'tok'}
        mock_get.return_value.ok = True
        mock_get.return_value.json.return_value = {
            'email': self.email,
            'name': 'Restricted Login',
            'sub': 'google-1',
        }
        session = self.client.session
        session['google_oauth_state'] = 'state-token'
        session.save()
        response = self.client.get(reverse('agents:google_auth_callback'), {
            'code': 'abc',
            'state': 'state-token',
        })
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, ACCOUNT_RESTRICTED_MESSAGE, status_code=403)
        self.assertNotIn('google_user', self.client.session)


class RestrictedPublicSurfaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='restricted-public@example.com',
            email='restricted-public@example.com',
            password='Password123',
        )
        self.agent = Agent.objects.create(
            user=self.user,
            fullname='Restricted Zebra Agent',
            email='restricted-public@example.com',
            mobile='9000008113',
            status='active',
            plan_type='starter',
        )
        self.profile = AgentProfile.objects.create(
            agent=self.agent,
            slug='restricted-zebra',
            display_name='Restricted Zebra Agent',
            is_profile_visible=True,
            is_card_visible=True,
        )
        AgentSubscription.objects.create(
            agent=self.agent,
            selected_plan="Starter's Plan",
            registration_amount=1999,
            payment_status='completed',
            status='active',
            razorpay_order_id='order_RESTRICT1',
            razorpay_payment_id='pay_RESTRICT1',
        )
        SiteSetting.set_value('qr_service_config', {'enabled': True, 'allow_download': True}, 'pricing')
        SiteSetting.set_value('agent_digital_card_enabled', True, group='general')

    def test_public_pages_hide_restricted_agent(self):
        card_url = reverse('agents:agent_public_card', kwargs={'slug': 'restricted-zebra'})
        visible = self.client.get(card_url)
        self.assertEqual(visible.status_code, 200)
        self.assertContains(visible, 'Restricted Zebra Agent')
        self.assertTrue(listed_agents_queryset().filter(pk=self.agent.pk).exists())

        self.agent.is_account_active = False
        self.agent.save(update_fields=['is_account_active'])

        card = self.client.get(card_url)
        self.assertEqual(card.status_code, 404)
        self.assertNotContains(card, 'Restricted Zebra Agent', status_code=404)

        profile = self.client.get(reverse('agents:agent_public_profile', kwargs={'slug': 'restricted-zebra'}))
        self.assertEqual(profile.status_code, 404)
        self.assertNotContains(profile, 'Restricted Zebra Agent', status_code=404)

        review = self.client.get(reverse('agents:agent_review_card', kwargs={'slug': 'restricted-zebra'}))
        self.assertEqual(review.status_code, 404)
        self.assertNotContains(review, 'Restricted Zebra Agent', status_code=404)

        review_page = self.client.get(reverse('agents:agent_public_review', kwargs={'slug': 'restricted-zebra'}))
        self.assertEqual(review_page.status_code, 404)
        self.assertNotContains(review_page, 'Restricted Zebra Agent', status_code=404)

        vcard = self.client.get(reverse('agents:agent_card_vcf', kwargs={'slug': 'restricted-zebra'}))
        self.assertEqual(vcard.status_code, 404)
        self.assertNotIn(b'Restricted Zebra Agent', vcard.content)

        qr = self.client.get(reverse(
            'agents:agent_public_qr_image',
            kwargs={'slug': 'restricted-zebra', 'qr_type': 'reviews'},
        ))
        self.assertEqual(qr.status_code, 404)
        self.assertNotIn(b'Restricted Zebra Agent', qr.content)

        posted = self.client.post(
            reverse('agents:agent_store_review', kwargs={'slug': 'restricted-zebra'}),
            {'rating': '5', 'review': 'This review must not be stored here.'},
        )
        self.assertEqual(posted.status_code, 404)
        self.assertFalse(listed_agents_queryset().filter(pk=self.agent.pk).exists())

    def test_restrict_deletes_the_open_browser_session(self):
        from django.contrib.sessions.models import Session
        from apps.admin_panel.views.agents import toggle_account

        self.client.force_login(self.user)
        session_key = self.client.session.session_key
        self.assertTrue(Session.objects.filter(session_key=session_key).exists())

        request = RequestFactory().post(
            '/admin/agents/toggle-account/',
            data=json.dumps({'id': self.agent.pk, 'active': False}),
            content_type='application/json',
        )
        request.session = {}
        request.admin_user = SimpleNamespace(role='staff', permissions=['agents'])
        with patch('apps.admin_panel.views.agents._get_admin_from_session', return_value=1):
            response = toggle_account(request)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())

        follow = self.client.get(reverse('agents:agent_dashboard'), follow=True)
        self.assertFalse(follow.wsgi_request.user.is_authenticated)

    def test_open_session_is_sent_back_to_login(self):
        self.agent.is_account_active = False
        self.agent.save(update_fields=['is_account_active'])
        self.client.force_login(self.user)
        response = self.client.get(reverse('agents:agent_dashboard'), follow=True)
        self.assertContains(response, ACCOUNT_RESTRICTED_MESSAGE)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
