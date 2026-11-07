"""Audit 2026-11-07 step 9: shared {% admin_pagination %} keeps all filters, URL-encoded."""
from django.core.paginator import Paginator
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase


class AdminPaginationTagTests(SimpleTestCase):
    def render(self, query, number, total=500):
        page = Paginator(range(total), 10).get_page(number)
        request = RequestFactory().get("/admin/x/", query)
        return Template("{% load admin_tags %}{% admin_pagination page %}").render(
            Context({"page": page, "request": request}))

    def test_keeps_filters_encoded_and_replaces_page(self):
        html = self.render({"search": "a&b #1", "status": "active", "page": "3"}, 3)
        self.assertIn("search=a%26b+%231", html)
        self.assertIn("status=active", html)
        self.assertIn("page=4", html)
        self.assertNotIn("page=3&amp;page", html)

    def test_long_ranges_are_elided(self):
        html = self.render({}, 25)
        self.assertIn("…", html)
        self.assertIn(">50<", html)

    def test_single_page_renders_nothing(self):
        self.assertEqual(self.render({}, 1, total=5).strip(), "")
