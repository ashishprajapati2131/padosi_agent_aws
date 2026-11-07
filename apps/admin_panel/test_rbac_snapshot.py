"""RBAC safety net for the admin panel (audit 2026-11-07, Phase 2).

For every named route under /admin and /padosi-admin, records who
AdminPermissionMiddleware lets through:
  "public"      no admin session needed
  "super_only"  no staff permission set reaches it
  [perms...]    staff holding any one of these permission keys reach it

The result must equal rbac_snapshot.json. Any change in who can open what
(refactoring the permission map, splitting urls.py, a new route) fails this
test until the snapshot is regenerated on purpose and the diff reviewed:

    set UPDATE_RBAC_SNAPSHOT=1 && python manage.py test apps.admin_panel.test_rbac_snapshot
"""

import json
import os
import re
import uuid
from pathlib import Path
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import URLPattern, URLResolver, get_resolver
from django.urls.resolvers import RoutePattern

from apps.admin_panel.middleware import AdminPermissionMiddleware
from apps.admin_panel.models.admin_auth import Admin
from apps.admin_panel.views.admins import get_permissions_list

SNAPSHOT = Path(__file__).with_name("rbac_snapshot.json")
ADMIN_PREFIXES = ("/admin", "/padosi-admin")

_SAMPLE = {"int": "1", "str": "x", "slug": "x", "path": "x", "uuid": str(uuid.UUID(int=1))}
_PARAM = re.compile(r"<(?:(\w+):)?\w+>")


def _admin_routes(patterns=None, prefix=""):
    """Yield (route string, url name, sample path) for every named /admin route.

    The path is built from the route itself (not reverse()), so routes that share
    a name are each checked at their own address.
    """
    patterns = get_resolver().url_patterns if patterns is None else patterns
    for p in patterns:
        if not isinstance(p.pattern, RoutePattern):
            continue  # regex routes: none under /admin today
        route = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            yield from _admin_routes(p.url_patterns, route)
        elif isinstance(p, URLPattern) and p.name:
            path = "/" + _PARAM.sub(lambda m: _SAMPLE.get(m.group(1) or "str", "x"), route)
            if path.startswith(ADMIN_PREFIXES):
                yield route, p.name, path


class _Gate:
    """Run only AdminPermissionMiddleware and report whether the view was reached."""

    def __init__(self):
        self.reached = HttpResponse("reached")
        self.mw = AdminPermissionMiddleware(lambda request: self.reached)

    def reaches(self, path, admin):
        request = RequestFactory().get(path)
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        admin_id = admin.pk if admin else None
        with (
            patch(
                "apps.admin_panel.auth._get_admin_from_session",
                return_value=admin_id,
            ),
            patch.object(Admin.objects, "get", return_value=admin),
            patch(
                "apps.admin_panel.views.dashboard.admin_logout",
                return_value=HttpResponse("logout"),
            ),
        ):
            return self.mw(request) is self.reached


def build_snapshot():
    gate = _Gate()
    names = [name for _, name, _ in _admin_routes()]
    perm_keys = {k for p in get_permissions_list() for k in [p["key"]] + [c["key"] for c in p.get("children", [])]}
    for name in names:  # keys only reachable through the middleware map
        required = gate.mw.get_required_permission(name)
        perm_keys.update(
            required if isinstance(required, tuple) else [required] if required else []
        )
    perm_keys = sorted(perm_keys)

    super_admin = Admin(id=1, name="S", email="s@x", role="super")

    def staff(perms):
        return Admin(id=2, name="T", email="t@x", role="staff", permissions=list(perms))

    snapshot = {}
    for route, name, path in _admin_routes():
        if gate.reaches(path, None):
            access = "public"
        elif not gate.reaches(path, staff(perm_keys)):
            access = "super_only" if gate.reaches(path, super_admin) else "nobody"
        else:
            access = [
                p for p in perm_keys if gate.reaches(path, staff([p]))
            ] or "any_staff"
        snapshot[route] = {"name": name, "access": access}
    return snapshot


class RbacSnapshotTests(TestCase):
    def test_access_matches_snapshot(self):
        current = build_snapshot()
        if os.environ.get("UPDATE_RBAC_SNAPSHOT") == "1":
            SNAPSHOT.write_text(
                json.dumps(current, indent=1, sort_keys=True) + "\n", encoding="utf-8"
            )
            self.skipTest(f"Snapshot rewritten: {SNAPSHOT}")
        expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        changed = {
            r: (expected.get(r), current.get(r))
            for r in expected.keys() | current.keys()
            if expected.get(r) != current.get(r)
        }
        self.assertFalse(
            changed,
            "Admin RBAC changed (route: (snapshot, now)). Review, then regenerate "
            "the snapshot as described in this module's docstring:\n"
            + json.dumps(changed, indent=1, sort_keys=True),
        )

    def test_no_route_is_unreachable_or_open_to_every_staff(self):
        current = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        bad = {
            r: v for r, v in current.items() if v["access"] in ("nobody", "any_staff")
        }
        self.assertFalse(bad, bad)

    def test_super_only_routes_stay_super_only(self):
        # Spot-check the rules CLAUDE.md and the audit rely on.
        current = {
            v["name"]: v["access"]
            for v in json.loads(SNAPSHOT.read_text(encoding="utf-8")).values()
        }
        for name in (
            "admin_admins_index",
            "admin_admins_delete",
            "admin_settings_templates_update",
            "admin_delete_subscription",
        ):
            self.assertEqual(current.get(name), "super_only", name)
