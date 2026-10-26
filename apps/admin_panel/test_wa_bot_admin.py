"""
Unit tests for WhatsApp & OpenWA Admin Command Center and Security Controls.
Run: python manage.py test apps.admin_panel.test_wa_bot_admin
"""

import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import AnonymousUser
from apps.admin_panel.models.admin_auth import Admin
from apps.wa_agent_bot.models import WaBotSession, WaBotMessageLog
from apps.agents.models import Agent, AgentSubscription
from apps.admin_panel.views.wa_bot_admin import (
    wa_bot_dashboard,
    wa_bot_sessions_list,
    wa_bot_logs_list,
    wa_bot_security_status,
    wa_bot_toggle_service,
    wa_bot_session_action,
    wa_bot_get_qr_ajax,
    wa_bot_send_test_message,
    wa_bot_reset_session,
    wa_bot_resend_credentials,
    wa_bot_save_config,
    wa_bot_sync_webhook,
    wa_bot_list_remote_sessions,
)


class WaBotAdminTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.admin = Admin.objects.create(
            name='Test Admin',
            email='admin@padosiagent.com',
            password='secret_password',
            role='super',
        )
        self.session_data = {
            'admin_id': self.admin.pk,
            'admin_role': 'super',
        }
        self.agent = Agent.objects.create(
            fullname='Kishor Patel',
            email='kishor@example.com',
            mobile='9825000000',
            status='pending_approval',
        )
        self.bot_session = WaBotSession.objects.create(
            phone_number='919825000000',
            state=WaBotSession.STATE_AWAITING_PAYMENT,
            agent=self.agent,
            registration_data={'fullname': 'Kishor Patel', 'email': 'kishor@example.com'},
        )
        self.log = WaBotMessageLog.objects.create(
            session=self.bot_session,
            direction=WaBotMessageLog.DIRECTION_IN,
            content='Hi, I want to register',
            state_at_time=WaBotSession.STATE_WELCOME,
        )

    def _auth_request(self, req):
        req.session = dict(self.session_data)
        req.user = AnonymousUser()
        return req

    @patch('apps.wa_agent_bot.services.openwa_admin_service.get_openwa_session_status')
    @patch('apps.wa_agent_bot.services.openwa_admin_service.get_openwa_qr_code')
    def test_dashboard_renders_for_admin(self, mock_qr, mock_status):
        mock_status.return_value = {
            'online': True,
            'latency_ms': 12,
            'status': 'qr_ready',
            'is_connected': False,
            'is_qr_ready': True,
            'phone': '919825000000',
            'push_name': 'PadosiAgent Bot',
        }
        mock_qr.return_value = {
            'success': True,
            'qr_code': 'data:image/png;base64,iVBORw0KG...',
            'status': 'qr_ready',
        }

        req = self._auth_request(self.factory.get('/admin/whatsapp/'))
        with patch('apps.admin_panel.views.wa_bot_admin._get_admin_from_session', return_value=self.admin.pk):
            resp = wa_bot_dashboard(req)
            self.assertEqual(resp.status_code, 200)

    @patch('apps.wa_agent_bot.services.openwa_admin_service.get_openwa_session_status', return_value={'online': False})
    @patch('apps.wa_agent_bot.services.openwa_admin_service.get_openwa_qr_code', return_value={'success': False})
    def test_dashboard_renders_visitor_without_registration_data(self, _mock_qr, _mock_status):
        """A brand-new visitor (no agent, empty registration_data) must not 500 the dashboard."""
        WaBotSession.objects.create(phone_number='919800000001', registration_data={})
        req = self._auth_request(self.factory.get('/admin/whatsapp/'))
        with patch('apps.admin_panel.views.wa_bot_admin._get_admin_from_session', return_value=self.admin.pk):
            resp = wa_bot_dashboard(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('New Visitor', resp.content.decode('utf-8'))

    @patch.dict('os.environ', {'WA_BOT_OPENWA_SESSION_ID': ''})
    @patch('apps.home.models.site_setting.SiteSetting.get_value', return_value=None)
    def test_openwa_status_reports_missing_config(self, _mock_setting):
        """With no session id configured the QR panel must say why instead of spinning forever."""
        from apps.wa_agent_bot.services.openwa_admin_service import get_openwa_session_status
        status = get_openwa_session_status()
        self.assertEqual(status['status'], 'not_configured')
        self.assertIn('not configured', status['error'])

    def test_toggle_lead_alerts_flips_flag(self):
        from apps.admin_panel.views.wa_bot_admin import wa_bot_toggle_lead_alerts
        from apps.wa_agent_bot.services.notification_service import lead_alerts_enabled
        self.assertFalse(lead_alerts_enabled())
        with patch('apps.admin_panel.views.wa_bot_admin._get_admin_from_session', return_value=self.admin.pk):
            req = self._auth_request(self.factory.post('/admin/whatsapp/toggle-lead-alerts/'))
            self.assertTrue(json.loads(wa_bot_toggle_lead_alerts(req).content)['enabled'])
            self.assertTrue(lead_alerts_enabled())
            req = self._auth_request(self.factory.post('/admin/whatsapp/toggle-lead-alerts/'))
            self.assertFalse(json.loads(wa_bot_toggle_lead_alerts(req).content)['enabled'])
            self.assertFalse(lead_alerts_enabled())

    def test_dashboard_redirects_unauthenticated(self):
        req = self.factory.get('/admin/whatsapp/')
        req.session = {}
        resp = wa_bot_dashboard(req)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin', resp.url)

    def test_sessions_list_renders_and_filters(self):
        req = self._auth_request(self.factory.get('/admin/whatsapp/sessions/?q=9825000000'))
        with patch('apps.admin_panel.views.wa_bot_admin._get_admin_from_session', return_value=self.admin.pk):
            resp = wa_bot_sessions_list(req)
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, '919825000000')

    def test_logs_list_renders_and_filters(self):
        req = self._auth_request(self.factory.get('/admin/whatsapp/logs/?direction=in'))
        with patch('apps.admin_panel.views.wa_bot_admin._get_admin_from_session', return_value=self.admin.pk):
            resp = wa_bot_logs_list(req)
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, 'Hi, I want to register')

    def test_security_status_renders(self):
        req = self._auth_request(self.factory.get('/admin/whatsapp/security/'))
        with patch('apps.admin_panel.views.wa_bot_admin._get_admin_from_session', return_value=self.admin.pk):
            resp = wa_bot_security_status(req)
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, 'Security Hardening Matrix')

    def test_toggle_bot_service(self):
        req = self._auth_request(self.factory.post('/admin/whatsapp/toggle-bot/'))
        with patch('apps.admin_panel.views.wa_bot_admin._get_admin_from_session', return_value=self.admin.pk):
            resp = wa_bot_toggle_service(req)
            self.assertEqual(resp.status_code, 200)
            import json
            data = json.loads(resp.content)
            self.assertTrue(data['success'])

    @patch('apps.admin_panel.views.wa_bot_admin.control_openwa_session')
    def test_session_action(self, mock_control):
        mock_control.return_value = (True, "Session restarted")
        req = self._auth_request(self.factory.post('/admin/whatsapp/session-action/', {'action': 'restart'}))
        with patch('apps.admin_panel.views.wa_bot_admin._get_admin_from_session', return_value=self.admin.pk):
            resp = wa_bot_session_action(req)
            self.assertEqual(resp.status_code, 200)
            import json
            data = json.loads(resp.content)
            self.assertTrue(data['success'])
            mock_control.assert_called_once_with('restart')

    def test_reset_session(self):
        req = self._auth_request(self.factory.post(f'/admin/whatsapp/reset-session/{self.bot_session.pk}/'))
        with patch('apps.admin_panel.views.wa_bot_admin._get_admin_from_session', return_value=self.admin.pk):
            resp = wa_bot_reset_session(req, self.bot_session.pk)
            self.assertEqual(resp.status_code, 200)
            self.bot_session.refresh_from_db()
            self.assertEqual(self.bot_session.state, WaBotSession.STATE_WELCOME)
            self.assertEqual(self.bot_session.registration_data, {})

    @patch('apps.admin_panel.views.wa_bot_admin.send_admin_test_whatsapp')
    def test_send_test_message(self, mock_send):
        mock_send.return_value = (True, "Message sent successfully!")
        req = self._auth_request(self.factory.post('/admin/whatsapp/send-test/', {
            'phone': '919825000000',
            'text': 'Test message from admin',
        }))
        with patch('apps.admin_panel.views.wa_bot_admin._get_admin_from_session', return_value=self.admin.pk):
            resp = wa_bot_send_test_message(req)
            self.assertEqual(resp.status_code, 200)
            import json
            data = json.loads(resp.content)
            self.assertTrue(data['success'])
            mock_send.assert_called_once_with('919825000000', 'Test message from admin')

    @patch('apps.admin_panel.views.wa_bot_admin.get_openwa_session_status')
    def test_save_remote_config(self, mock_status):
        mock_status.return_value = {'online': True, 'latency_ms': 25, 'status': 'connected'}
        req = self._auth_request(self.factory.post('/admin/whatsapp/save-config/', {
            'base_url': 'https://wa.padosiagent.com',
            'session_id': 'remote-session-1234',
            'api_key': 'secret-owa-key',
        }))
        with patch('apps.admin_panel.views.wa_bot_admin._get_admin_from_session', return_value=self.admin.pk):
            resp = wa_bot_save_config(req)
            self.assertEqual(resp.status_code, 200)
            import json
            data = json.loads(resp.content)
            self.assertTrue(data['success'])
            self.assertTrue(data['online'])

            from apps.home.models.site_setting import SiteSetting
            self.assertEqual(SiteSetting.get_value('wa_bot_openwa_base_url'), 'https://wa.padosiagent.com')
            self.assertEqual(SiteSetting.get_value('wa_bot_openwa_session_id'), 'remote-session-1234')

    @patch('apps.admin_panel.views.wa_bot_admin.sync_openwa_webhook')
    def test_sync_webhook(self, mock_sync):
        mock_sync.return_value = (True, "Webhook synced successfully")
        req = self._auth_request(self.factory.post('/admin/whatsapp/sync-webhook/', {
            'webhook_url': 'https://padosiagent.com/wa-bot/webhook/',
        }))
        with patch('apps.admin_panel.views.wa_bot_admin._get_admin_from_session', return_value=self.admin.pk):
            resp = wa_bot_sync_webhook(req)
            self.assertEqual(resp.status_code, 200)
            import json
            data = json.loads(resp.content)
            self.assertTrue(data['success'])
            mock_sync.assert_called_once_with('https://padosiagent.com/wa-bot/webhook/')

    @patch('apps.admin_panel.views.wa_bot_admin.list_openwa_sessions')
    def test_list_remote_sessions(self, mock_list):
        mock_list.return_value = (True, [{'id': 'test-session-id', 'name': 'padosi'}], None)
        req = self._auth_request(self.factory.get('/admin/whatsapp/list-sessions/'))
        with patch('apps.admin_panel.views.wa_bot_admin._get_admin_from_session', return_value=self.admin.pk):
            resp = wa_bot_list_remote_sessions(req)
            self.assertEqual(resp.status_code, 200)
            import json
            data = json.loads(resp.content)
            self.assertTrue(data['success'])
            self.assertEqual(len(data['sessions']), 1)
            self.assertEqual(data['sessions'][0]['id'], 'test-session-id')


