"""Audit 2026-11-07 step 9: the sidebar shows exactly the admin routes the RBAC middleware opens
(nav_open comes from registry.ROUTE_PERMISSIONS)."""
import re
from urllib.parse import urlparse

from django.template.loader import get_template
from django.test import RequestFactory, TestCase
from django.urls import resolve

from apps.admin_panel.registry import iter_modules, open_route_names


PUBLIC = {"admin_logout", "admin_login", "admin_login_page"}


def _sidebar_routes(perms, is_super=False):
    request = RequestFactory().get("/admin/dashboard/")
    html = get_template("admin/base.html").render(
        {"request": request, "is_super_admin": is_super, "admin_permissions": set(perms),
         "nav_open": open_route_names(perms, is_super)}, request)
    names = set()
    for href in re.findall(r'<a\s+href="(/admin[^"]*)"\s+class="menu-item', html):
        names.add(resolve(urlparse(href).path).url_name)
    return names - PUBLIC


class SidebarFollowsRegistryTests(TestCase):
    def test_every_sidebar_link_is_openable(self):
        for module in iter_modules():
            perms = [module.key]
            open_names = open_route_names(perms, False)
            shown = _sidebar_routes(perms)
            self.assertFalse(shown - open_names, f"{module.key}: dead links {sorted(shown - open_names)}")

    def test_super_admin_sees_reconcile_and_staff_does_not(self):
        self.assertIn("admin_payment_reconcile", _sidebar_routes([], is_super=True))
        self.assertNotIn("admin_payment_reconcile", _sidebar_routes(["invoices", "revenue"]))
