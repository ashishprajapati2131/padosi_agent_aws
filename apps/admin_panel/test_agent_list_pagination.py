"""Audit 2026-10-01 F-37: the admin agent list loaded every agent (with three
correlated subqueries each) to show 25. It now counts, then fetches one page."""
from unittest.mock import patch

from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

from apps.admin_panel.views.agents import agent_list
from apps.agents.models import Agent


class AgentListPaginationTests(TestCase):
    def setUp(self):
        for i in range(30):
            Agent.objects.create(fullname=f'Agent {i:02d}', email=f'list{i:02d}@example.com',
                                 mobile=f'90000003{i:02d}', status='active')
        Agent.objects.create(fullname='Hidden', email='inactive@example.com', mobile='9000000399', status='inactive')

    def _get(self, **params):
        request = RequestFactory().get('/admin/agents/', params)
        request.session = {}
        with patch('apps.admin_panel.views.agents._get_admin_from_session', return_value=1), \
             patch('apps.admin_panel.context_processors.admin_badge_counts', return_value={}), \
             patch('apps.admin_panel.views.agents.render') as render:
            render.side_effect = lambda req, tpl, ctx: ctx
            with CaptureQueriesContext(connection) as queries:
                ctx = agent_list(request)
                page = ctx['page_obj']
                rows = list(page)
        return page, rows, [q['sql'] for q in queries.captured_queries]

    def test_first_page_newest_first_and_total(self):
        page, rows, sqls = self._get()
        self.assertEqual(page.paginator.count, 30)
        self.assertEqual(len(rows), 25)
        self.assertEqual(rows[0]['email'], 'list29@example.com')
        self.assertEqual(page.paginator.num_pages, 2)
        self.assertTrue(any('LIMIT' in sql for sql in sqls))
        self.assertTrue(any(sql.startswith('SELECT COUNT(*) FROM agents') for sql in sqls))

    def test_second_page_has_the_rest(self):
        page, rows, _ = self._get(page='2')
        self.assertEqual([r['email'] for r in rows], [f'list{i:02d}@example.com' for i in range(4, -1, -1)])
        self.assertEqual((page.start_index(), page.end_index()), (26, 30))

    def test_filters_and_bad_page_still_work(self):
        page, rows, _ = self._get(search='Agent 07')
        self.assertEqual([r['email'] for r in rows], ['list07@example.com'])
        page, rows, _ = self._get(status='inactive')
        self.assertEqual([r['email'] for r in rows], ['inactive@example.com'])
        page, rows, _ = self._get(page='99')          # out of range -> last page, as before
        self.assertEqual(page.number, 2)
        page, rows, _ = self._get(search='nobody-matches')
        self.assertEqual((page.paginator.count, rows), (0, []))
