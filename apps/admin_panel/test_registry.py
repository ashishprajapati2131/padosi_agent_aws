"""Consistency checks for apps/admin_panel/registry.py (the admin module / access registry)."""

from django.test import SimpleTestCase
from django.urls import get_resolver

from apps.admin_panel import registry


def _url_names():
    names = set()

    def walk(patterns):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                walk(p.url_patterns)
            elif p.name:
                names.add(p.name)

    walk(get_resolver().url_patterns)
    return names


class RegistryTests(SimpleTestCase):
    def test_module_keys_are_unique(self):
        keys = [m.key for m in registry.iter_modules()]
        self.assertEqual(len(keys), len(set(keys)), keys)

    def test_every_mapped_route_exists(self):
        missing = sorted(set(registry.ROUTE_PERMISSIONS) - _url_names())
        self.assertFalse(
            missing, f"ROUTE_PERMISSIONS names with no URL pattern: {missing}"
        )

    def test_every_mapped_permission_is_a_declared_module(self):
        declared = {m.key for m in registry.iter_modules()}
        used = set()
        for perm in registry.ROUTE_PERMISSIONS.values():
            used.update(perm if isinstance(perm, tuple) else (perm,))
        self.assertFalse(
            used - declared, f"Undeclared permission keys: {sorted(used - declared)}"
        )

    def test_landing_route_is_open_to_that_permission(self):
        # A staff member holding only this key must be able to open where they land.
        for module in registry.iter_modules():
            if not module.default_route:
                continue
            perm = registry.required_permission(module.default_route)
            allowed = perm if isinstance(perm, tuple) else (perm,)
            parent_ok = module.key.startswith("approvals_") and "approvals" in allowed
            self.assertTrue(
                module.key in allowed or parent_ok,
                f"{module.key} lands on {module.default_route}, which requires {perm}",
            )

    def test_landing_route_follows_module_order(self):
        self.assertEqual(registry.landing_route(["users", "invoices"]), "admin_users")
        self.assertEqual(registry.landing_route(["invoices"]), "admin_invoices")
        self.assertIsNone(registry.landing_route([]))
        # Review 2026-11-07: this key landed on the dashboard it cannot open (redirect loop).
        self.assertIsNone(registry.landing_route(["fastapi_services"]))
        self.assertEqual(registry.landing_route(["fastapi_services", "logs"]), "admin_system_logs")
