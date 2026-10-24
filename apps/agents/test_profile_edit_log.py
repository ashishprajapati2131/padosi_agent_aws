"""Agent profile saves are recorded so the admin approval drawer can show what changed."""
import json
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.agents.models import Agent, AgentProfile, AgentProfileEditLog
from apps.agents.views.dashboard import _log_profile_edit, _profile_edit_snapshot
from apps.admin_panel.views.agents import get_edit_logs


class ProfileEditLogTests(TestCase):
    def test_agent_edit_is_logged_and_shown_escaped_to_admin(self):
        agent = Agent.objects.create(fullname='Old Name', email='log@example.com',
                                     mobile='9876543210', status='active')
        profile = AgentProfile.objects.create(agent=agent, address='Ahmedabad')
        before = _profile_edit_snapshot(agent, profile)

        agent.fullname = '<b>New</b>'
        agent.status = 'pending_approval'
        profile.address = 'Surat'
        request = RequestFactory().post('/agent/profile/update/')
        request.session = {}
        _log_profile_edit(request, agent, before, _profile_edit_snapshot(agent, profile), '7', False)

        log = AgentProfileEditLog.objects.get(agent=agent)
        self.assertEqual((log.edited_by, log.step, log.status_before, log.status_after),
                         ('agent', 7, 'active', 'pending_approval'))

        with patch('apps.admin_panel.views.agents._get_admin_from_session', return_value=1):
            data = json.loads(get_edit_logs(RequestFactory().get('/'), agent.id).content)
        self.assertTrue(data['success'])
        changes = {c['field']: c for c in data['logs'][0]['changes']}
        self.assertEqual(changes['profile.address']['new_value'], 'Surat')
        self.assertEqual(changes['fullname']['new_value'], '&lt;b&gt;New&lt;/b&gt;')

    def test_no_change_writes_no_log(self):
        agent = Agent.objects.create(fullname='Same', email='same@example.com',
                                     mobile='9876543210', status='active')
        profile = AgentProfile.objects.create(agent=agent)
        snap = _profile_edit_snapshot(agent, profile)
        request = RequestFactory().post('/')
        request.session = {}
        _log_profile_edit(request, agent, snap, dict(snap), '1', False)
        self.assertFalse(AgentProfileEditLog.objects.filter(agent=agent).exists())


class AppProfileEditLogTests(SimpleTestCase):
    """Mobile app (FastAPI) saves write the same log rows."""

    def test_app_edit_is_logged(self):
        from fastapi_app.models.agent import Agent as SaAgent
        from fastapi_app.models.agent_profile import AgentProfile as SaProfile
        from fastapi_app.services.profile_service import ProfileService

        agent = SaAgent(id=5, fullname='Old', status='active')
        agent.profile = SaProfile(agent_id=5, address='Ahmedabad')
        before = ProfileService._edit_snapshot(agent)
        agent.fullname = 'New'
        agent.profile.address = 'Surat'
        agent.status = 'pending_approval'

        db = MagicMock()
        ProfileService(MagicMock())._log_profile_edit(db, agent, before, 1, 'Basic Info')

        log = db.add.call_args.args[0]
        self.assertEqual((log.edited_by, log.step, log.step_label, log.status_before, log.status_after),
                         ('agent', 1, 'Basic Info (App)', 'active', 'pending_approval'))
        self.assertEqual({c['field'] for c in log.changes}, {'fullname', 'profile.address'})

    def test_app_unchanged_save_writes_nothing(self):
        from fastapi_app.models.agent import Agent as SaAgent
        from fastapi_app.services.profile_service import ProfileService

        agent = SaAgent(id=6, fullname='Same', status='active')
        db = MagicMock()
        ProfileService(MagicMock())._log_profile_edit(db, agent, ProfileService._edit_snapshot(agent), 1, 'Basic Info')
        db.add.assert_not_called()
