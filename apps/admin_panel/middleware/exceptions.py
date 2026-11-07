"""Log unhandled exceptions to the ErrorLog table."""
import logging
import traceback
import sys
from apps.admin_panel.models.error_log import ErrorLog
from .security import ThreatMonitorMiddleware

logger = logging.getLogger(__name__)


class ExceptionLoggerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 0. Fast-path whitelist for health checks, probes, and static metadata
        if request.path in ["/health/", "/healthz", "/favicon.ico", "/robots.txt"]:
            return self.get_response(request)
        return self.get_response(request)

    def process_exception(self, request, exception):
        try:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
            stack_trace = "".join(tb_lines)

            # Identify user
            user_info = None
            try:
                if (
                    hasattr(request, "session")
                    and request.session
                    and request.session.get("admin_id")
                ):
                    user_info = f"Admin: {request.session.get('admin_name', 'N/A')} ({request.session.get('admin_email', 'N/A')})"
                elif hasattr(request, "user") and request.user.is_authenticated:
                    user_info = f"User: {request.user.username}"
            except Exception:
                pass

            # Get IP address (trusted-proxy rule, not the spoofable first hop)
            ip = ThreatMonitorMiddleware.get_client_ip(request)

            # Log to Database
            ErrorLog.objects.create(
                level="ERROR",
                module=exception.__class__.__module__,
                exception_type=exception.__class__.__name__,
                message=str(exception),
                stack_trace=stack_trace,
                url=request.build_absolute_uri(),
                method=request.method,
                user_info=user_info,
                status_code=500,
                ip_address=ip,
            )
        except Exception:
            # Module logger goes to console/file only (no DB handler), so this can't recurse.
            logger.exception("ExceptionLoggerMiddleware could not write ErrorLog")
        return None
