from django.contrib.auth.models import AnonymousUser
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponse
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase

from apps.admin_panel.middleware import AdminPermissionMiddleware
from apps.home.services.portal_messages import (
    PORTAL_ADMIN,
    PORTAL_AGENT,
    message_is_for_portal,
    message_is_success,
    portal_success,
)


class _Msg:
    def __init__(self, text, tags):
        self.tags = tags
        self.message = text

    def __str__(self):
        return self.message


class PortalMessageFilterTests(SimpleTestCase):
    def test_admin_tagged_error_is_hidden_from_agent_portal(self):
        message = _Msg('Please sign in to access the admin panel.', 'portal-admin error')
        self.assertTrue(message_is_for_portal(message, PORTAL_ADMIN))
        self.assertFalse(message_is_for_portal(message, PORTAL_AGENT))
        self.assertFalse(message_is_success(message))

    def test_agent_logout_success_stays_green_with_portal_tag(self):
        message = _Msg('You have been logged out successfully.', 'portal-agent success')
        self.assertTrue(message_is_for_portal(message, PORTAL_AGENT))
        self.assertFalse(message_is_for_portal(message, PORTAL_ADMIN))
        self.assertTrue(message_is_success(message))

    def test_legacy_admin_copy_without_tag_stays_on_admin_login(self):
        message = _Msg('Please sign in to access the admin panel.', 'error')
        self.assertTrue(message_is_for_portal(message, PORTAL_ADMIN))
        self.assertFalse(message_is_for_portal(message, PORTAL_AGENT))


class PortalMessageLeakTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _prepare(self, path):
        request = self.factory.get(path)
        request.session = {}
        request._messages = FallbackStorage(request)
        request.user = AnonymousUser()
        return request

    def test_admin_gate_flash_is_not_for_agent_login(self):
        request = self._prepare('/admin/agents/')
        response = AdminPermissionMiddleware(lambda req: HttpResponse('ok'))(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login', response.url)

        queued = list(get_messages(request))
        self.assertTrue(any('admin panel' in str(message) for message in queued))
        self.assertFalse(any(message_is_for_portal(message, PORTAL_AGENT) for message in queued))
        self.assertTrue(any(message_is_for_portal(message, PORTAL_ADMIN) for message in queued))
        self.assertFalse(any(message_is_success(message) for message in queued))

        html = Template(
            "{% load portal_messages %}"
            "{% for message in messages %}"
            "{% if message|for_portal:'agent' %}LEAK:{{ message }}{% endif %}"
            "{% endfor %}"
        ).render(Context({'messages': queued}))
        self.assertNotIn('LEAK:', html)

    def test_agent_logout_success_renders_green_not_red(self):
        request = self._prepare('/agent-logout/')
        portal_success(request, 'You have been logged out successfully.', PORTAL_AGENT)
        queued = list(get_messages(request))
        html = Template(
            "{% load portal_messages %}"
            "{% for message in messages %}"
            "{% if message|for_portal:'agent' %}"
            "<div class=\"{% if message|is_success_message %}alert-success-custom{% else %}alert-danger-custom{% endif %}\">{{ message }}</div>"
            "{% endif %}"
            "{% endfor %}"
        ).render(Context({'messages': queued}))
        self.assertIn('alert-success-custom', html)
        self.assertNotIn('alert-danger-custom', html)
        self.assertIn('logged out successfully', html)
