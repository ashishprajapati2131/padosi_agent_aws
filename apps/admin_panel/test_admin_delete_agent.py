"""Audit 2026-10-01 F-41: admin "delete agent" hard-deleted the row with
FOREIGN_KEY_CHECKS=0 (orphaning its subscriptions and invoices) and suspended
the `users` row whose id equals agents.user_id (a Django auth_user id, i.e.
possibly a different person)."""
import json
from unittest.mock import patch

from django.contrib.auth.models import User as AuthUser
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.admin_panel.models.users import User as LaravelUser
from apps.agents.models import Agent, AgentSubscription


class AdminDeleteAgentTests(TestCase):
    def setUp(self):
        self.auth_user = AuthUser.objects.create_user('del.agent', 'del.agent@example.com', 'x')
        self.stranger = LaravelUser.objects.create(id=self.auth_user.id, fullname='Stranger', email='stranger.del@example.com',
                                                   password='$2y$10$x', role='agent', status='active')
        self.own = LaravelUser.objects.create(fullname='Del', email='del.agent@example.com',
                                              password='$2y$10$x', role='agent', status='active')
        self.agent = Agent.objects.create(user=self.auth_user, fullname='Del', email='del.agent@example.com',
                                          mobile='9000000181', status='active')
        self.sub = AgentSubscription.objects.create(
            agent=self.agent, selected_plan="Starter's Plan", registration_amount='2359.00',
            payment_status='completed', status='active', razorpay_order_id='order_DELAGENT00001')

    def _delete(self):
        from apps.admin_panel.views.delete import admin_delete
        request = RequestFactory().post('/admin/delete/', data=json.dumps({'model': 'agent', 'id': self.agent.pk}),
                                        content_type='application/json')
        request.session = {}
        with patch('apps.admin_panel.views.delete._get_admin_from_session', return_value=1):
            return json.loads(admin_delete(request).content)

    def test_paid_agent_is_soft_deleted_and_records_kept(self):
        body = self._delete()
        self.assertTrue(body['success'], body)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, 'deleted')
        self.assertTrue(AgentSubscription.objects.filter(pk=self.sub.pk).exists())

    def test_only_the_agents_own_users_row_is_suspended(self):
        self._delete()
        self.stranger.refresh_from_db()
        self.own.refresh_from_db()
        self.assertEqual((self.stranger.status, self.own.status), ('active', 'suspended'))


class DeletedAgentApiLoginTests(SimpleTestCase):
    def test_deleted_agents_are_blocked_in_the_api(self):
        from fastapi_app.dependencies.auth import BLOCKED_AGENT_STATUSES as dep_blocked
        from fastapi_app.services.auth_service import BLOCKED_AGENT_STATUSES as login_blocked
        self.assertIn('deleted', dep_blocked)
        self.assertIn('deleted', login_blocked)
