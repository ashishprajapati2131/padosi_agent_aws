"""Smoke test: every admin GET page opens for a Super Admin without a server error.

Set ADMIN_SMOKE_REPORT=<path> to write {route: status} JSON (used to compare two versions).
"""

import json
import os
import re
from datetime import datetime, timedelta

from django.test import TestCase
from django.urls import URLPattern, URLResolver, get_resolver
from django.urls.resolvers import RoutePattern

SAMPLE = {
    "int": "1",
    "str": "x",
    "slug": "x",
    "path": "x",
    "uuid": "00000000-0000-0000-0000-000000000001",
}
PARAM = re.compile(r"<(?:(\w+):)?\w+>")
# Not pages: file downloads/streams, logout, and actions that run jobs on GET.
SKIP_NAMES = {
    "admin_logout",
    "admin_system_download_backup",
    "admin_system_run_backup",
    "admin_system_run_jobs",
}


# These pages run MySQL-only SQL (DATE_FORMAT, TIMESTAMPDIFF, NOW(), ...) or read a table the
# SQLite test DB lacks; they 500 here before and after the audit alike (verified against the
# pre-audit commit). They are exercised on MySQL, not by this test.
KNOWN_MYSQL_ONLY = {
    "admin/export/pending/",
    "admin/finance/",
    "admin/free-trial/",
    "admin/free-trial/analytics-data/",
    "admin/free-trial/history/",
    "admin/insurance-approvals/",
    "admin/insurance-approvals/<int:id>/process/",
    "admin/leads/",
    "admin/revenue/",
}


def admin_get_routes(patterns=None, prefix=""):
    patterns = get_resolver().url_patterns if patterns is None else patterns
    for p in patterns:
        if not isinstance(p.pattern, RoutePattern):
            continue
        route = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            yield from admin_get_routes(p.url_patterns, route)
        elif isinstance(p, URLPattern) and p.name and p.name not in SKIP_NAMES:
            path = "/" + PARAM.sub(
                lambda m: SAMPLE.get(m.group(1) or "str", "x"), route
            )
            if path.startswith("/admin"):
                yield route, p.name, path


class AdminSmokeTests(TestCase):
    def setUp(self):
        from django.db import connection

        from apps.admin_panel.models.admin_auth import Admin

        self.admin = Admin.objects.create(
            name="Smoke", email="smoke@example.com", password="x", role="super"
        )
        now = datetime.now()
        with connection.cursor() as cursor:
            # Raw token: both old (plaintext) and new (hashed, legacy-compatible) code accept it.
            cursor.execute(
                "INSERT INTO user_sessions (session_token, admin_id, last_activity, expires_at, created_at, updated_at)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                ["smoke-token", self.admin.pk, now, now + timedelta(days=1), now, now],
            )
            session_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO user_session_data (session_id, data_key, data_value, created_at, updated_at)"
                " VALUES (%s, 'admin_id', %s, %s, %s)",
                [session_id, str(self.admin.pk), now, now],
            )
        self.client.cookies["session_token"] = "smoke-token"
        self.client.raise_request_exception = False

    def test_admin_pages_do_not_error(self):
        results, errors = {}, {}
        for route, name, path in admin_get_routes():
            try:
                status = self.client.get(path).status_code
            except Exception as exc:  # noqa: BLE001 - record and continue
                status = f"EXC {type(exc).__name__}"
            results[route] = status
            if (status == 500 or str(status).startswith("EXC")) and route not in KNOWN_MYSQL_ONLY:
                errors[route] = status
        report = os.environ.get("ADMIN_SMOKE_REPORT")
        if report:
            with open(report, "w", encoding="utf-8") as fh:
                json.dump(results, fh, indent=1, sort_keys=True)
            return
        self.assertFalse(errors, f"Admin pages failing: {json.dumps(errors, indent=1)}")
