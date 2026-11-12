"""WAF / threat monitor, client IP helpers and IP blocking."""

import logging
import re
import threading
import json
from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.conf import settings
from django.template.loader import render_to_string
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from apps.admin_panel.views.security import BlockedIp, SecurityThreatLog
from apps.admin_panel.services.brevo import send_brevo_email


# Bounded so the scan stays linear: the old greedy `{{[\s\S]*}}` was quadratic and a
# ~20 KB body of "{{" held a worker for seconds (ReDoS on every public request).
_TEMPLATE_TAG_RE = re.compile(
    r"(\{\{[^}]{0,200}\}\}|\{%[^%]{0,200}%\}|\[\[[^\]]{0,200}\]\])"
)
# shortcut: only the first 64 KB of request data is scanned; raise if payloads hide past it.
_WAF_SCAN_LIMIT = 65536

logger = logging.getLogger(__name__)


def client_ip_from_forwarded_for(x_forwarded_for):
    """Real client IP from an X-Forwarded-For chain received via a trusted proxy.

    Proxies APPEND the address they saw, so the left-most entries are whatever
    the client sent. Walk from the right, skipping internal proxy hops
    (private / loopback), and return the first public address. Taking entry
    [0] let anyone spoof their IP — dodging rate limits and getting arbitrary
    IPs (e.g. shared mobile CGNAT addresses) auto-blocked.
    """
    import ipaddress

    hops = [h.strip() for h in (x_forwarded_for or "").split(",") if h.strip()]
    valid = []
    for hop in hops:
        try:
            valid.append((hop, ipaddress.ip_address(hop)))
        except ValueError:
            continue
    for hop, addr in reversed(valid):
        if not (addr.is_private or addr.is_loopback or addr.is_link_local):
            return hop
    if valid:
        return valid[0][0]
    return "127.0.0.1"


AUTO_BLOCK_PREFIX = "Auto-blocked"
AUTO_BLOCK_TTL_HOURS = 24


_BLOCKED_SET_KEY = "waf_blocked_ip_set_v1"


def _blocked_ip_set():
    """All blocked IPs as one cached set (60s; cleared on any BlockedIp change).

    Caching per visitor IP wrote one file-cache entry per IP per minute, and every
    FileBasedCache write lists the whole cache dir (and culls site settings).
    """
    try:
        cached = cache.get(_BLOCKED_SET_KEY)
        if cached is not None:
            return cached
    except Exception:
        pass
    ips = frozenset(BlockedIp.objects.values_list("ip_address", flat=True))
    try:
        cache.set(_BLOCKED_SET_KEY, ips, timeout=60)
    except Exception:
        pass
    return ips


@receiver(post_save, sender=BlockedIp)
@receiver(post_delete, sender=BlockedIp)
def _clear_blocked_ip_set(**kwargs):
    cache.delete(_BLOCKED_SET_KEY)


def is_ip_blocked(ip):
    """True if the IP is blocked. Automatic blocks expire after 24 hours."""
    if not ip or ip in ("127.0.0.1", "::1"):
        return False
    if ip not in _blocked_ip_set():
        return False

    block = BlockedIp.objects.filter(ip_address=ip).first()
    if not block:
        return False
    reason = block.reason or ""
    created = getattr(block, "created_at", None)
    if reason.startswith(AUTO_BLOCK_PREFIX) and created:
        from datetime import datetime, timedelta

        try:
            expired = created < datetime.now() - timedelta(hours=AUTO_BLOCK_TTL_HOURS)
        except TypeError:  # aware vs naive datetime from legacy rows
            expired = False
        if expired:
            try:
                block.delete()
            except Exception:
                logger.warning("Could not lift expired auto-block for %s", ip)
            return False
    return True


# Compiled once (they were re-parsed from strings on every request).
_WAF_PATTERN_SOURCES = {
    "SQL Injection": r"(union select\s|select\s+\*\s+from|insert\s+into|update\s+\w+\s+set|'\s*or\s*'1'\s*=\s*'1|sleep\(\d+\)|benchmark\s*\(|group_concat|information_schema)",
    "Cross Site Scripting (XSS)": r"(<script\b[^>]*>|javascript:|onerror=|onload=|eval\(|setTimeout\(|setInterval\(|alert\(|document\.cookie|document\.domain|window\.location)",
    "Path Traversal / LFI": r"((?<!\.)\.\.[/\\]|\/etc\/passwd|\/etc\/shadow|\/etc\/group|\/etc\/hosts|\/proc\/self|php:\/\/filter|php:\/\/input|expect:\/\/)",
    "RCE / Shell Injection": r"(system\(|exec\(|passthru\(|shell_exec\(|proc_open\(|pcntl_exec\(|python\s+-c|perl\s+-e|ruby\s+-e|bash\s+-i|nc\s+-e)",
    "SSRF / Metadata API": r"(169\.254\.169\.254|metadata\.google\.internal|\/latest\/meta-data\/)",
    "XML External Entity (XXE)": r"(<!ENTITY\s+|SYSTEM\s+[\"']|PUBLIC\s+[\"'])",
    "Server-Side Template Injection": _TEMPLATE_TAG_RE.pattern,
    "CRLF / Header Injection": r"(\%0d\%0a|Set-Cookie:|Content-Type:)",
}
_WAF_PATTERNS = {
    k: re.compile(v, re.IGNORECASE) for k, v in _WAF_PATTERN_SOURCES.items()
}


class ThreatMonitorMiddleware:
    """
    Web Application Firewall (WAF) and Threat Monitor Middleware.
    Mirrors Laravel's ThreatMonitorMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def get_client_ip(request):
        remote_addr = request.META.get("REMOTE_ADDR", "")
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        # Only trust X-Forwarded-For if direct connection is a local trusted proxy
        if remote_addr in ["127.0.0.1", "::1"] and x_forwarded_for:
            return client_ip_from_forwarded_for(x_forwarded_for)
        return remote_addr or "127.0.0.1"

    def __call__(self, request):
        # 0. Fast-path whitelist for health checks, probes, and static metadata
        if request.path.startswith("/health/") or request.path in [
            "/healthz",
            "/favicon.ico",
            "/robots.txt",
        ]:
            return self.get_response(request)
        # 1. Get Client IP Address safely
        remote_addr = request.META.get("REMOTE_ADDR", "")
        ip = self.get_client_ip(request)

        # 2. Whitelist local/trusted IPs only if direct connection is genuinely local
        if remote_addr in ["127.0.0.1", "::1"] and ip in ["127.0.0.1", "::1"]:
            return self.get_response(request)

        # 3. Check if IP is already explicitly Blocked
        if is_ip_blocked(ip):
            if request.headers.get(
                "accept"
            ) == "application/json" or request.path.startswith("/api/"):
                return JsonResponse(
                    {
                        "error": "Forbidden",
                        "message": "Your IP address has been blocked.",
                    },
                    status=403,
                )
            return HttpResponseForbidden(
                "Your IP address has been blocked due to suspicious activity."
            )

        # 4. Identify potential Malicious Payloads (Basic WAF functionality)
        url_to_check = request.build_absolute_uri()

        # Check if user is an authenticated Admin (to allow safe HTML and template saving)
        is_admin = False
        try:
            from apps.admin_panel.auth import _get_admin_from_session

            if _get_admin_from_session(request):
                is_admin = True
        except Exception:
            pass

        if not is_admin:
            try:
                if (
                    hasattr(request, "session")
                    and request.session
                    and (
                        request.session.get("admin_id")
                        or request.session.get("admin_user_id")
                        or request.session.get("admin_name")
                        or request.session.get("is_admin")
                        or request.session.get("user_type") == "admin"
                    )
                ):
                    is_admin = True
            except Exception:
                pass

        if not is_admin:
            try:
                if (
                    hasattr(request, "user")
                    and request.user.is_authenticated
                    and (request.user.is_staff or request.user.is_superuser)
                ):
                    is_admin = True
            except Exception:
                pass

        is_admin_path = (
            request.path.startswith("/admin/")
            or request.path.startswith("/padosi-admin/")
            or request.path.startswith("/django-admin/")
        )
        if is_admin_path and not is_admin:
            try:
                if (
                    hasattr(request, "session")
                    and request.session
                    and request.session.get("admin_id")
                ):
                    is_admin = True
            except Exception:
                pass

        safe_html_fields = [
            "file_content",
            "content",
            "html_content",
            "template",
            "email_body",
            "email_header",
            "html_code",
            "config_json",
            "digital_price",
            "professional_price",
            "modal_title",
            "modal_subtitle",
            "tab_review_label",
            "tab_social_label",
            "config",
            "settings",
            "json_data",
            "template_text",
            "body",
            "message",
            "subject",
            "description",
            "custom_css",
            "custom_js",
            "html",
            "raw_html",
            "payload",
            "json_config",
            "badge_title",
            "badge_subtitle",
            "cta_button_text",
            "nudge_title",
            "nudge_message",
            "nudge_yes_text",
            "nudge_skip_text",
            "dashboard_section_title",
            "dashboard_section_desc",
            "dashboard_url_placeholder",
        ]

        # Collect request input fields
        payload_dict = {}
        if request.method in ["POST", "PUT", "PATCH"]:
            # Try to load POST parameters
            for k, v in request.POST.items():
                if (is_admin or is_admin_path) and (
                    k in safe_html_fields or "{{" in str(v) or "{%" in str(v)
                ):
                    v_clean = re.sub(
                        _TEMPLATE_TAG_RE,
                        "[TEMPLATE_TAG]",
                        str(v),
                    )
                    payload_dict[k] = v_clean
                else:
                    payload_dict[k] = v
            # If JSON body, try parsing it
            try:
                if request.content_type == "application/json" and request.body:
                    json_data = json.loads(
                        request.body.decode("utf-8", errors="ignore")
                    )
                    if isinstance(json_data, dict):
                        for k, v in json_data.items():
                            if is_admin or is_admin_path:
                                v_clean = re.sub(
                                    _TEMPLATE_TAG_RE,
                                    "[TEMPLATE_TAG]",
                                    str(v),
                                )
                                payload_dict[k] = v_clean
                            else:
                                payload_dict[k] = v
            except Exception:
                pass

        # Include GET parameters too
        for k, v in request.GET.items():
            payload_dict[k] = v

        input_str = json.dumps(payload_dict)[:_WAF_SCAN_LIMIT]
        input_str_for_crlf = input_str.replace("\\r\\n", " ").replace("\r\n", " ")

        # Hardened WAF regex patterns
        patterns = _WAF_PATTERNS

        matched_type = None
        for threat_type, pattern in patterns.items():
            if threat_type == "Server-Side Template Injection" and (
                is_admin or is_admin_path
            ):
                continue
            str_to_check = (
                input_str_for_crlf
                if threat_type == "CRLF / Header Injection"
                else input_str
            )
            if pattern.search(str_to_check) or pattern.search(url_to_check):
                matched_type = threat_type
                break

        if matched_type:
            # 5. Profile Hacker
            hacker_name = "GUEST / ANONYMOUS"
            hacker_email = None
            hacker_mobile = None

            # Get admin credentials from session if present
            try:
                if (
                    hasattr(request, "session")
                    and request.session
                    and request.session.get("admin_id")
                ):
                    hacker_name = f"Admin: {request.session.get('admin_name', 'N/A')}"
                    hacker_email = request.session.get("admin_email")
            except Exception:
                pass

            # Fallback to general django auth user if present
            if (
                hacker_name == "GUEST / ANONYMOUS"
                and hasattr(request, "user")
                and request.user.is_authenticated
            ):
                hacker_name = request.user.get_full_name() or request.user.username
                hacker_email = request.user.email
                # Try to fetch mobile from Client profile if it exists
                try:
                    from apps.agents.models import Client

                    client = Client.objects.filter(user=request.user).first()
                    if client:
                        hacker_mobile = client.mobile
                except Exception:
                    pass

            # 6. Location / Geo-IP Details (non-blocking, avoids external HTTP DoS vulnerability)
            location = "Unknown Location"
            isp = "Unknown ISP"

            # 7. Auto-Block check (3 offenses in last 1 hour)
            one_hour_ago = timezone.now() - timezone.timedelta(hours=1)
            recent_offenses = SecurityThreatLog.objects.filter(
                ip_address=ip, created_at__gte=one_hour_ago
            ).count()

            is_auto_blocked = False
            # If they already have 2 offenses, this current offense is the 3rd, triggering auto-ban
            if recent_offenses >= 2:
                BlockedIp.objects.get_or_create(
                    ip_address=ip,
                    defaults={
                        "reason": f"Auto-blocked by Threat Monitor due to recurring malicious payloads ({matched_type})."
                    },
                )
                is_auto_blocked = True

            # 8. Save Security Threat Log Record
            SecurityThreatLog.objects.create(
                ip_address=ip,
                event_type=matched_type,
                hacker_name=hacker_name,
                hacker_email=hacker_email,
                hacker_mobile=hacker_mobile,
                location=location,
                isp=isp,
                url=url_to_check,
                payload=input_str[:1000],
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )

            # 9. Send Security Alert Email to Admin via Brevo service (throttled to avoid DoS)
            email_cache_key = f"threat_email_alert_{ip}"
            if is_auto_blocked and not cache.get(email_cache_key):
                try:
                    cache.set(
                        email_cache_key, True, timeout=600
                    )  # Throttled: max 1 email per 10 min per blocked IP
                    threat_context = {
                        "ip_address": ip,
                        "event_type": matched_type,
                        "timestamp": timezone.now().strftime("%d %b %Y, %I:%M %p"),
                        "url": url_to_check,
                        "payload": input_str[:500],
                        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
                        "hacker_name": hacker_name,
                        "hacker_email": hacker_email,
                        "location": location,
                        "isp": isp,
                        "is_blocked": is_auto_blocked,
                    }
                    html_body = render_to_string(
                        "emails/security_threat.html", {"threat": threat_context}
                    )
                    # No personal address in code: unset -> the site's own sender mailbox.
                    alert_email = (
                        getattr(settings, "SECURITY_ALERT_EMAIL", "").strip()
                        or getattr(settings, "DEFAULT_FROM_EMAIL", "").strip()
                    )
                    if not alert_email:
                        raise ValueError("SECURITY_ALERT_EMAIL is not configured")
                    # Off the request thread: Brevo has a 20 s timeout and this runs inside a 403 response.
                    threading.Thread(
                        target=send_brevo_email,
                        kwargs={
                            "to_email": alert_email,
                            "to_name": "Admin",
                            "subject": "⚠️ SECURITY ALERT: Malicious Activity Detected on PadosiAgent",
                            "html_content": html_body,
                        },
                        daemon=True,
                    ).start()
                except Exception as e:
                    logger.error(
                        f"ThreatMonitorMiddleware: Failed to send security email alert: {e}"
                    )

            # Return 403 response
            if request.headers.get(
                "accept"
            ) == "application/json" or request.path.startswith("/api/"):
                return JsonResponse(
                    {"error": "Malicious Activity Detected."}, status=403
                )
            return HttpResponseForbidden("Malicious Activity Detected.")

        return self.get_response(request)
