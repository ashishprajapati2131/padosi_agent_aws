"""Audit 2026-10-01 F-24: admin agent status changes accepted any status
string, bulk-approved arbitrary ids, failed with an error after the change was
already saved, and Approvals-only staff could not act on their own queue."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.agents.models import Agent


class AgentStatusActionTests(TestCase):
    def setUp(self):
        self.queued = Agent.objects.create(fullname='Q', email='queued@example.com', mobile='9000000111',
                                           status='pending_approval')
        self.active = Agent.objects.create(fullname='A', email='activeone@example.com', mobile='9000000112',
                                           status='active')

    def _toggle(self, agent, status, perms=None, role='staff'):
        from apps.admin_panel.views.agents import toggle_status
        request = RequestFactory().post('/admin/agents/toggle-status/', data=json.dumps({'id': agent.pk, 'status': status}),
                                        content_type='application/json')
        request.session = {}
        request.admin_user = SimpleNamespace(role=role, permissions=perms if perms is not None else ['agents'])
        with patch('apps.admin_panel.views.agents._get_admin_from_session', return_value=1):
            resp = toggle_status(request)
        agent.refresh_from_db()
        return resp.status_code, json.loads(resp.content)

    def test_unknown_status_is_rejected(self):
        code, _ = self._toggle(self.active, 'activ3')
        self.assertEqual(code, 400)
        self.assertEqual(self.active.status, 'active')

    def test_agents_staff_can_still_suspend_and_reactivate(self):
        self.assertEqual(self._toggle(self.active, 'suspended')[1]['success'], True)
        self.assertEqual(self.active.status, 'suspended')
        self.assertEqual(self._toggle(self.active, 'active')[1]['success'], True)
        self.assertEqual(self.active.status, 'active')

    def test_approvals_only_staff_can_decide_the_queue_only(self):
        perms = ['approvals_awaiting_verification']
        code, body = self._toggle(self.queued, 'active', perms=perms)
        self.assertTrue(body['success'], body)
        self.assertEqual(self.queued.status, 'active')
        code, _ = self._toggle(self.active, 'suspended', perms=perms)
        self.assertEqual(code, 403)
        self.assertEqual(self.active.status, 'active')

    def test_audit_log_failure_no_longer_reports_an_error(self):
        with patch('apps.admin_panel.models.agent_profile_edit_log.AgentProfileEditLog.objects.create',
                   side_effect=Exception('log table down')):
            code, body = self._toggle(self.queued, 'active')
        self.assertEqual((code, body['success']), (200, True))
        self.assertEqual(self.queued.status, 'active')

    def test_bulk_approve_only_touches_the_queue(self):
        from apps.admin_panel.views.agents import bulk_action_agents
        suspended = Agent.objects.create(fullname='S', email='susp@example.com', mobile='9000000113', status='suspended')
        request = RequestFactory().post('/admin/agents/bulk/', {
            'action': 'approve', 'agent_ids[]': [self.queued.pk, suspended.pk]})
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch('apps.admin_panel.views.agents._get_admin_from_session', return_value=1):
            bulk_action_agents(request)
        self.queued.refresh_from_db()
        suspended.refresh_from_db()
        self.assertEqual((self.queued.status, suspended.status), ('active', 'suspended'))

    def test_approve_route_admits_the_approvals_permission(self):
        from apps.admin_panel.middleware import AdminPermissionMiddleware
        middleware = AdminPermissionMiddleware(lambda r: None)
        self.assertEqual(middleware.get_required_permission('admin_agents_toggle_status'), ('agents', 'approvals'))
        self.assertEqual(middleware.get_required_permission('admin_agents_bulk_action'), ('agents', 'approvals'))
