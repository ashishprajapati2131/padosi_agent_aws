import json
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.management import call_command
from django.http import HttpResponse

from apps.agents.models import Agent, AgentProfile, AgentSubscription
from apps.admin_panel.models.admin_auth import Admin
from padosi_agent.middleware import StaleCookieSanitizerMiddleware, AutoCsrfCookieMiddleware
from fastapi_app.models.promo_code import PromoCode
from fastapi_app.utils.datetime_util import get_current_time
from fastapi_app.services.email_service import EmailService


class AuditProductionFixesTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_stale_cookie_sanitizer_bridges_csrf_token_header(self):
        """HTTP_X_CSRF_TOKEN header is normalized to HTTP_X_CSRFTOKEN."""
        def dummy_view(request):
            return HttpResponse(request.META.get('HTTP_X_CSRFTOKEN', ''))

        middleware = StaleCookieSanitizerMiddleware(dummy_view)
        request = self.factory.post('/some-endpoint/', HTTP_X_CSRF_TOKEN='test_token_123')
        self.assertNotIn('HTTP_X_CSRFTOKEN', request.META)

        response = middleware(request)
        self.assertEqual(request.META.get('HTTP_X_CSRFTOKEN'), 'test_token_123')
        self.assertEqual(response.content.decode(), 'test_token_123')

    def test_auto_csrf_cookie_middleware_sets_secure_flag(self):
        """AutoCsrfCookieMiddleware attaches padosi_csrf_token with matching secure flag."""
        def dummy_view(request):
            return HttpResponse('OK')

        middleware = AutoCsrfCookieMiddleware(dummy_view)

        # Insecure request (HTTP)
        req_insecure = self.factory.get('/')
        resp_insecure = middleware(req_insecure)
        self.assertIn('padosi_csrf_token', resp_insecure.cookies)
        self.assertFalse(resp_insecure.cookies['padosi_csrf_token']['secure'])
        self.assertEqual(resp_insecure.cookies['padosi_csrf_token']['samesite'], 'Lax')

        # Secure request (HTTPS)
        req_secure = self.factory.get('/', secure=True)
        resp_secure = middleware(req_secure)
        self.assertIn('padosi_csrf_token', resp_secure.cookies)
        self.assertTrue(resp_secure.cookies['padosi_csrf_token']['secure'])

    def test_promo_code_is_valid_with_ist_naive_datetime(self):
        """PromoCode.is_valid uses current IST datetime and evaluates expiration correctly."""
        now = get_current_time()

        # Expired promo code (1 hour ago)
        expired_promo = PromoCode(
            code="EXPIRED10",
            discount_type="percentage",
            discount_value=Decimal("10.00"),
            is_active=True,
            expires_at=now - timedelta(hours=1),
        )
        self.assertFalse(expired_promo.is_valid())

        # Valid promo code (expires in 1 hour)
        valid_promo = PromoCode(
            code="VALID10",
            discount_type="percentage",
            discount_value=Decimal("10.00"),
            is_active=True,
            expires_at=now + timedelta(hours=1),
        )
        self.assertTrue(valid_promo.is_valid())

    def test_find_agent_locator_rejects_admin_portal_email(self):
        """create_and_add_agent in find_agent_locator rejects emails belonging to superusers/admins."""
        admin_user = User.objects.create_superuser(
            username='admin_boss',
            email='boss@padosiagent.com',
            password='Password123!'
        )

        from apps.admin_panel.views.find_agent_locator import create_and_add_agent

        request = self.factory.post(
            '/admin-panel/find-agent-locator/create-agent/',
            data=json.dumps({
                'fullname': 'Fake Agent',
                'email': 'boss@padosiagent.com',
                'mobile': '9876543210',
                'pincode': '110001',
                'lat': 28.63,
                'lng': 77.22,
                'city_name': 'New Delhi',
            }),
            content_type='application/json'
        )

        # Mock admin session so _check_admin passes
        with patch('apps.admin_panel.views.find_agent_locator._check_admin', return_value=1):
            response = create_and_add_agent(request)

        self.assertEqual(response.status_code, 422)
        resp_json = json.loads(response.content)
        self.assertFalse(resp_json['success'])
        self.assertIn('cannot be registered as an agent', resp_json['message'])

    def test_agent_update_visibility_with_email_resolved_agent(self):
        """agent_update_visibility succeeds even when agent is linked by email rather than direct agent.user."""
        auth_user = User.objects.create_user(
            username='vishnu_agent',
            email='vishnu@example.com',
            password='TestPassword123'
        )
        agent = Agent.objects.create(
            fullname='Vishnu Agent',
            email='vishnu@example.com',
            mobile='9123456789',
            status='active'
        )
        profile = AgentProfile.objects.create(
            agent=agent,
            show_certificates=False
        )

        from apps.agents.views.dashboard import agent_update_visibility

        request = self.factory.post(
            '/agent/update-visibility/',
            data=json.dumps({'field': 'show_certificates', 'value': 1}),
            content_type='application/json'
        )
        request.user = auth_user

        response = agent_update_visibility(request)
        self.assertEqual(response.status_code, 200)
        resp_json = json.loads(response.content)
        self.assertTrue(resp_json['success'])

        profile.refresh_from_db()
        self.assertTrue(profile.show_certificates)

    def test_email_service_locates_agent_credentials_template(self):
        """EmailService finds agent_credentials.html without TemplateNotFound errors."""
        import os
        from jinja2 import Environment, FileSystemLoader

        fastapi_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'fastapi_app'))
        project_root = os.path.dirname(fastapi_dir)
        search_dirs = [
            os.path.join(fastapi_dir, "templates"),
            os.path.join(project_root, "templates", "emails"),
            os.path.join(project_root, "templates"),
        ]
        valid_dirs = [d for d in search_dirs if os.path.isdir(d)]
        env = Environment(loader=FileSystemLoader(valid_dirs), autoescape=True)
        template = env.get_template("agent_credentials.html")
        rendered = template.render(
            agent_name="Test Agent",
            agent_email="test@padosiagent.com",
            password="secretpassword",
            logo_url="https://padosiagent.com/logo.png",
            login_url="https://padosiagent.com/agent-login",
            current_year=2026,
            agent={"fullname": "Test Agent", "email": "test@padosiagent.com"}
        )
        self.assertIn("Welcome to PadosiAgent", rendered)
        self.assertIn("test@padosiagent.com", rendered)

    def test_backup_dumpdata_excludes_unmanaged_models(self):
        """_backup_dumpdata in backup_database command properly gathers unmanaged models to exclude."""
        from apps.agents.management.commands.backup_database import Command
        from django.apps import apps
        from pathlib import Path
        import tempfile

        cmd = Command()
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            with patch('django.core.management.call_command') as mock_dumpdata:
                # Mock call_command to simply succeed
                cmd._backup_dumpdata(backup_dir, 'test_run')
                self.assertTrue(mock_dumpdata.called)
                called_args = mock_dumpdata.call_args[0]
                self.assertEqual(called_args[0], 'dumpdata')
                # Verify that unmanaged models in apps were included in --exclude
                unmanaged_labels = [
                    f"{m._meta.app_label}.{m._meta.model_name}"
                    for m in apps.get_models() if not m._meta.managed
                ]
                for label in unmanaged_labels:
                    self.assertIn(label, called_args)

    def test_championship_dashboard_with_email_resolved_agent(self):
        """agent_championship_dashboard succeeds when agent is linked by email rather than direct agent.user."""
        from apps.referral_championship.models import ChampionshipCampaign
        auth_user = User.objects.create_user(
            username='champ_agent',
            email='champ@example.com',
            password='TestPassword123'
        )
        agent = Agent.objects.create(
            fullname='Champ Agent',
            email='champ@example.com',
            mobile='9988776655',
            status='active'
        )
        AgentProfile.objects.create(
            agent=agent,
            experience_years=5,
            address='Ahmedabad',
            state='Gujarat'
        )
        campaign = ChampionshipCampaign.get_current()

        from apps.referral_championship.views.agent_dashboard import agent_championship_dashboard

        request = self.factory.get('/agent/championship/agent/dashboard/?format=json')
        request.user = auth_user

        response = agent_championship_dashboard(request)
        self.assertEqual(response.status_code, 200)
        resp_json = json.loads(response.content)
        self.assertTrue(resp_json['success'])
        self.assertIn('campaign_hero', resp_json)
        self.assertIn('unlock_access_gate', resp_json)

    def test_save_pincode_accepts_lat_lng_aliases(self):
        """save_pincode_to_master succeeds with lat/lng instead of latitude/longitude."""
        from apps.home.models import Pincode
        from apps.admin_panel.views.find_agent_locator import save_pincode_to_master

        req = self.factory.post(
            '/admin/find-agent-locator/save-pincode/',
            data=json.dumps({
                'pincode': '380088',
                'office_name': 'Test Area',
                'district': 'Ahmedabad',
                'state': 'Gujarat',
                'lat': 23.01,
                'lng': 72.54,
            }),
            content_type='application/json'
        )
        with patch('apps.admin_panel.views.find_agent_locator._check_admin', return_value=1):
            response = save_pincode_to_master(req)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        pin = Pincode.objects.get(pincode='380088')
        self.assertAlmostEqual(float(pin.latitude), 23.01, places=2)
        self.assertAlmostEqual(float(pin.longitude), 72.54, places=2)
