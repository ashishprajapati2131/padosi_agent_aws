"""Audit 2026-10-01 F-40: paid signups store plan_type='starter', but the
revenue page counted only 'basic', so Starter agents and Starter MRR showed 0.
The view's SQL is MySQL-only, so a recording cursor checks what it asks."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.admin_panel.views import revenue


class _RecordingCursor:
    def __init__(self, calls):
        self.calls = calls
        self.description = []

    def execute(self, sql, params=None):
        self.calls.append((sql, list(params or [])))

    def fetchone(self):
        return (0,)

    def fetchall(self):
        return []


class RevenueStarterPlanTests(SimpleTestCase):
    def test_starter_agents_and_mrr_include_starter_slug(self):
        calls = []

        @contextmanager
        def cursor():
            yield _RecordingCursor(calls)

        with patch.object(revenue, '_get_admin_from_session', return_value=1), \
             patch.object(revenue, 'connection', SimpleNamespace(cursor=cursor)), \
             patch.object(revenue, 'render', side_effect=lambda req, tpl, ctx: ctx):
            revenue.revenue_dashboard(RequestFactory().get('/admin/revenue/'))

        count_sql = [sql for sql, _ in calls if sql.startswith('SELECT COUNT(*) FROM agents') and 'basic' in sql]
        self.assertEqual(len(count_sql), 1)
        self.assertIn("'starter'", count_sql[0])
        mrr_params = [params for sql, params in calls if 'TIMESTAMPDIFF' in sql]
        self.assertEqual(mrr_params, [['professional'], ['basic', 'starter']])
        mrr_sql = [sql for sql, _ in calls if 'TIMESTAMPDIFF' in sql]
        self.assertIn('IN (%s)', mrr_sql[0])
        self.assertIn('IN (%s, %s)', mrr_sql[1])
