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


class WebEditToAdminDrawerTests(TestCase):
    """Real HTTP path: agent edits on the website, admin drawer endpoint lists the changes."""

    def test_agent_web_edit_reaches_admin_drawer(self):
        from django.contrib.auth.models import User
        from django.core.cache import cache
        from django.urls import reverse
        from apps.agents.models import AgentSubscription
        cache.clear()
        user = User.objects.create_user('edit_agent', 'edit@example.com', 'pw12345!')
        agent = Agent.objects.create(user=user, fullname='Edit Agent', email='edit@example.com',
                                     mobile='9876500009', status='active', plan_type='starter',
                                     experience_range='2')
        AgentProfile.objects.create(agent=agent, slug='edit-agent', languages='Gujarati',
                                    address='Ahmedabad')
        agent.insuranceSegments.create(segment_type='life')
        AgentSubscription.objects.create(agent=agent, selected_plan="Starter's Plan",
                                         registration_amount=1999, payment_status='completed',
                                         status='active', razorpay_order_id='order_EDITLOG0001',
                                         razorpay_payment_id='pay_EDITLOG0001')
        self.client.force_login(user)
        url = reverse('agents:agent_update_profile')
        base = {'full_name': 'Edit Agent', 'mobile': '9876500009', 'address': 'Ahmedabad'}

        r1 = self.client.post(url, {**base, 'languages': 'Gujarati, Hindi', 'current_step': 1})
        self.assertEqual(r1.status_code, 200, r1.content)
        r2 = self.client.post(url, {'experience_years': '8', 'client_base': '100',
                                    'service_pincode': '380001', 'serviceable_cities[]': ['Ahmedabad'],
                                    'current_step': 2})
        self.assertEqual(r2.status_code, 200, r2.content)
        # Web visual step 3 posts backend step 4, which saves segments.
        r3 = self.client.post(url, {'segments[]': ['life', 'health'], 'current_step': 4})
        self.assertEqual(r3.status_code, 200, r3.content)
        r4 = self.client.post(url, {'current_step': 7})
        self.assertEqual(r4.status_code, 200, r4.content)

        with patch('apps.admin_panel.views.agents._get_admin_from_session', return_value=1):
            data = json.loads(get_edit_logs(RequestFactory().get('/'), agent.id).content)
        self.assertTrue(data['success'], data)
        fields = {c['field'] for log in data['logs'] for c in log['changes']}
        self.assertIn('profile.languages', fields, data)
        self.assertIn('experience_range', fields, data)
        seg = next(c for log in data['logs'] for c in log['changes'] if c['field'] == 'insurance_segments')
        self.assertEqual((seg['old_value'], seg['new_value']), ('life', 'health, life'))
        self.assertTrue(any(l['status_after'] == 'pending_approval' for l in data['logs']), data)


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
