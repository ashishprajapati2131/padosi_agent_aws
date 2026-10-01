"""Audit 2026-10-01 F-32: any admin with Invoices access could point the
invoice sync at any https site, which then received every invoice's PII and
PDF; only a hostname blocklist stood in the way."""
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.admin_panel.models.admin_auth import Admin


class AppsScriptUrlTests(SimpleTestCase):
    def test_only_apps_script_urls_are_allowed(self):
        from apps.agents.services.invoice import InvoiceService
        ok = InvoiceService.is_apps_script_url
        self.assertTrue(ok('https://script.google.com/macros/s/AKfycbx/exec'))
        self.assertTrue(ok('https://script.google.com/a/macros/padosiagent.com/s/AKfycbx/exec'))
        for bad in ('https://evil.example/collect', 'http://script.google.com/macros/s/x/exec',
                    'https://script.google.com.evil.example/x', 'https://evil.example/?script.google.com',
                    'https://user@evil.example/', '', None):
            self.assertFalse(ok(bad), bad)

    def test_sync_does_not_post_to_other_hosts(self):
        from apps.agents.services import invoice as invoice_module
        with patch.object(invoice_module, 'SiteSetting') as site_setting, \
             patch.object(invoice_module.requests, 'post') as post:
            site_setting.get_value.return_value = 'https://evil.example/collect'
            result = invoice_module.invoice_service.sync_to_google_sheet({'invoice_number': 'PA/1'})
        self.assertFalse(result)
        post.assert_not_called()


class SaveSheetUrlGuardTests(TestCase):
    def setUp(self):
        self.staff = Admin.objects.create(name='S', email='inv.staff@example.com', password='x', role='staff')
        self.super = Admin.objects.create(name='U', email='inv.super@example.com', password='x', role='super')

    def _save(self, admin, url):
        from apps.admin_panel.views.invoices import save_sheet_url
        request = RequestFactory().post('/admin/invoices/sheet-url/', {'sheet_url': url})
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        with patch('apps.admin_panel.views.invoices._get_admin_from_session', return_value=admin.pk), \
             patch('apps.admin_panel.views.invoices.connection') as conn:
            save_sheet_url(request)
        return conn.cursor.return_value.__enter__.return_value.execute.called

    def test_staff_cannot_change_the_sync_target(self):
        self.assertFalse(self._save(self.staff, 'https://script.google.com/macros/s/AKfycbx/exec'))

    def test_super_admin_cannot_save_a_foreign_host(self):
        self.assertFalse(self._save(self.super, 'https://evil.example/collect'))

    def test_super_admin_can_save_an_apps_script_url(self):
        self.assertTrue(self._save(self.super, 'https://script.google.com/macros/s/AKfycbx/exec'))
