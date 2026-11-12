"""Keep admin and agent sessions from leaking into each other."""


class IsolateAdminAgentSessionsMiddleware:
    """
    A Django-authenticated agent must not keep an admin session_token cookie.
    That cookie is what AdminPermissionMiddleware uses to grant /admin access.
    """

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
        if path in ["/admin", "/admin/login", "/admin/login/post", "/admin/logout"]:
            return self.get_response(request)

        token = request.COOKIES.get("session_token")
        user = getattr(request, "user", None)
        if token and user is not None and getattr(user, "is_authenticated", False):
            from django.core.cache import cache
            from apps.agents.models import Agent

            # Non-agent users with an admin cookie hit this on every request; cache the answer.
            key = f"is_agent_user_{user.pk}"
            is_agent = cache.get(key)
            if is_agent is None:
                is_agent = Agent.objects.filter(user_id=user.pk).exists()
                if not is_agent:
                    cache.set(key, False, timeout=300)
            if is_agent:
                from apps.admin_panel.auth import invalidate_admin_session_token

                invalidate_admin_session_token(token)
                request.COOKIES.pop("session_token", None)
                response = self.get_response(request)
                response.delete_cookie("session_token")
                return response
        return self.get_response(request)
