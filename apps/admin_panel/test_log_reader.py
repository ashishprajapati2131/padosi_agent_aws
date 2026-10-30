from pathlib import Path

from django.test import SimpleTestCase

from apps.admin_panel.services.log_reader import group_issues, parse_entries

BASE = Path('/srv/app')

LOG = '''[2026-10-27 00:56:07,434] ERROR apps.home.views.pages — Error in view: near "3": syntax error
Traceback (most recent call last):
  File "/usr/lib/python3/site-packages/django/db/backends/utils.py", line 105, in _execute
    return self.cursor.execute(sql, params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
sqlite3.OperationalError: near "3": syntax error

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/srv/app/apps/home/views/pages.py", line 691, in fetch_list
    all_agents = list(query)
  File "/usr/lib/python3/site-packages/django/db/models/query.py", line 400, in __iter__
    self._fetch_all()
django.db.utils.OperationalError: near "3": syntax error
[2026-10-27 01:00:00,000] WARNING django.request — Not Found: /card/a-1/
[2026-10-27 01:00:05,000] WARNING django.request — Not Found: /card/b-2/
[2026-10-27 01:00:09,000] ERROR apps.agents.services.brevo — Mail failed for 'x@y.com'
[2026-10-27 01:00:10,000] ERROR apps.agents.services.brevo — Mail failed for 'z@w.com'
'''


class LogReaderTests(SimpleTestCase):
    def setUp(self):
        self.entries = parse_entries(LOG, BASE)

    def test_traceback_is_attached_and_analysed(self):
        e = self.entries[0]
        self.assertEqual(len(self.entries), 5)
        self.assertEqual(e['exc_type'], 'django.db.utils.OperationalError')  # last raised, not the chained cause
        self.assertEqual((e['location']['file'], e['location']['line']), ('apps/home/views/pages.py', '691'))
        self.assertNotIn('^^^', e['stack'])
        self.assertIn('Database query failed', e['hint'])

    def test_http_entries(self):
        e = self.entries[1]
        self.assertEqual((e['http_status'], e['http_path']), (404, '/card/a-1/'))

    def test_repeats_group_into_one_issue(self):
        issues = group_issues(self.entries)
        self.assertEqual(len(issues), 3)
        top = issues[0]
        self.assertEqual(top['count'], 2)
        self.assertEqual(top['latest']['message'], "Mail failed for 'z@w.com'")
        self.assertEqual([i['count'] for i in issues[1:]], [2, 1])

    def test_logs_view_handles_future_timestamp(self):
        """A log line stamped slightly in the future lands in the current hour instead of a 500."""
        import tempfile
        from datetime import datetime, timedelta
        from unittest.mock import patch
        from django.test import RequestFactory, override_settings
        from apps.admin_panel.views import system

        future = (datetime.now() + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S,000')
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'django.log').write_text(f'[{future}] ERROR apps.x — clock skew\n', encoding='utf-8')
            with override_settings(LOGS_DIR=Path(tmp)), patch.object(system, 'render') as render:
                system.logs(RequestFactory().get('/admin/system/logs/'))
        buckets = render.call_args[0][2]['buckets']
        self.assertEqual(buckets[-1]['errors'], 1)
