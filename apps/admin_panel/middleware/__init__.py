"""Admin panel middlewares, split by concern (was one 1,100-line module).

settings.MIDDLEWARE and other modules keep importing from apps.admin_panel.middleware.
"""
from .security import (  # noqa: F401
    AUTO_BLOCK_PREFIX,
    AUTO_BLOCK_TTL_HOURS,
    ThreatMonitorMiddleware,
    _TEMPLATE_TAG_RE,
    _WAF_SCAN_LIMIT,
    _blocked_ip_set,
    client_ip_from_forwarded_for,
    is_ip_blocked,
)
from .ip_whitelist import AdminIpWhitelistMiddleware  # noqa: F401
from .session_isolation import IsolateAdminAgentSessionsMiddleware  # noqa: F401
from .rbac import AdminPermissionMiddleware  # noqa: F401
from .exceptions import ExceptionLoggerMiddleware  # noqa: F401
