"""Optional IP allow-list for /admin (ADMIN_WHITELIST_IPS)."""

import logging
from django.http import HttpResponseForbidden
from django.conf import settings
from .security import ThreatMonitorMiddleware

logger = logging.getLogger(__name__)


class AdminIpWhitelistMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 0. Fast-path whitelist for health checks, probes, and static metadata
        if request.path.startswith("/health/") or request.path in [
            "/healthz",
            "/favicon.ico",
            "/robots.txt",
        ]:
            return self.get_response(request)
        path = request.path.rstrip("/")
        if (
            path.startswith("/admin")
            or path.startswith("/padosi-admin")
            or path.startswith("/django-admin")
        ):
            # Trusted client IP: a raw X-Forwarded-For would let anyone claim a
            # whitelisted address.
            ip = ThreatMonitorMiddleware.get_client_ip(request)

            # Fetch whitelist from settings. Enforce only when configured.
            whitelist = getattr(settings, "ADMIN_WHITELIST_IPS", [])
            if not whitelist:
                return self.get_response(request)

            # Localhost always allowed
            allowed = set(whitelist) | {
                "127.0.0.1",
                "::1",
                "localhost",
                "testclient",
                "testserver",
            }
            if ip not in allowed:
                logger.warning(
                    f"Admin IP Whitelist: Blocked request from unauthorized IP: {ip} for path {request.path}"
                )
                return HttpResponseForbidden(
                    "Access Denied: IP address not authorized."
                )

        return self.get_response(request)
