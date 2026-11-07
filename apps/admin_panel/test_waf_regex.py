"""Audit 2026-11-07 P1: the WAF's greedy SSTI regex was quadratic (ReDoS on every public request)."""

import re
import time

from django.test import SimpleTestCase

from apps.admin_panel.middleware import _TEMPLATE_TAG_RE, _WAF_SCAN_LIMIT


class WafTemplateRegexTests(SimpleTestCase):
    def test_still_detects_template_injection(self):
        for payload in ("{{7*7}}", "{% load os %}", "[[ x ]]", "{{config.__class__}}"):
            self.assertTrue(
                re.search(_TEMPLATE_TAG_RE.pattern, payload, re.IGNORECASE), payload
            )

    def test_hostile_input_scans_fast(self):
        hostile = ("{{" * 1_250_000)[
            :_WAF_SCAN_LIMIT
        ]  # 2.5 MB body, capped as the middleware does
        start = time.monotonic()
        re.search(_TEMPLATE_TAG_RE.pattern, hostile, re.IGNORECASE)
        self.assertLess(time.monotonic() - start, 0.5)
