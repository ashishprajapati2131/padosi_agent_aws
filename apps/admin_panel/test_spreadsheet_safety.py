"""Audit 2026-10-01 F-28: exports and the Google Sheet sync wrote agent text
(names, emails, addresses, reviews) unescaped, so a value like =HYPERLINK(...)
ran as a formula when an admin opened the file."""
import csv
import io
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.admin_panel.services.spreadsheet_safety import safe_cell, safe_csv_writer


class SafeCellTests(SimpleTestCase):
    def test_formulas_are_neutralised(self):
        for value in ('=HYPERLINK("http://x","y")', '@SUM(A1)', '+cmd|calc', '-2+3+cmd|x', '\t=1'):
            self.assertTrue(safe_cell(value).startswith("'"), value)

    def test_normal_values_are_unchanged(self):
        for value in ('Ramesh Patel', 'agent@example.com', '+91 98765 43210', '-25.5', '9876543210', '', 12, None, 3.5):
            self.assertEqual(safe_cell(value), value)

    def test_safe_csv_writer(self):
        buf = io.StringIO()
        safe_csv_writer(buf).writerow(['=1+1', 'ok', 5])
        self.assertEqual(next(csv.reader(io.StringIO(buf.getvalue()))), ["'=1+1", 'ok', '5'])


class ExportUsesSafeWriterTests(TestCase):
    def test_csv_response_neutralises_rows(self):
        from apps.admin_panel.views.export import _csv_response
        resp = _csv_response('x.csv', ['Name'], [['=IMPORTXML("http://evil")']])
        body = resp.content.decode('utf-8-sig')
        self.assertIn("'=IMPORTXML", body)

    def test_sheet_payload_neutralises_agent_text(self):
        from apps.agents.services import invoice as invoice_module
        captured = {}

        class _Resp:
            status_code = 200
            text = '{"success": true}'

            def json(self):
                return {'success': True}

        def fake_post(url, json=None, **kwargs):
            captured.update(json or {})
            return _Resp()

        invoice = {'invoice_number': 'PA/1', 'agent_name': '=HYPERLINK("http://x")', 'agent_email': 'a@example.com',
                   'plan_name': "Starter's Plan", 'agent_state': 'Gujarat', 'total_amount': 100, 'gst_amount': 18,
                   'base_amount': 82, 'promo_code': '@x'}
        with patch.object(invoice_module.requests, 'post', side_effect=fake_post), \
             patch.object(invoice_module, 'SiteSetting') as site_setting:
            site_setting.get_value.return_value = 'https://script.google.com/macros/s/abc/exec'
            invoice_module.invoice_service.sync_to_google_sheet(invoice)
        self.assertTrue(captured, 'sheet sync did not post')
        if captured:
            self.assertTrue(captured['agent_name'].startswith("'"))
            self.assertTrue(captured['Agent'].startswith("'"))
            self.assertTrue(captured['promo_code'].startswith("'"))
