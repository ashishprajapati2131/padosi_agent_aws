"""Admin route gate: deny-by-default permission map keyed by url_name."""

from django.shortcuts import redirect

from apps.admin_panel import registry
from apps.home.services.portal_messages import PORTAL_ADMIN, portal_error


class AdminPermissionMiddleware:
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
        if not (path.startswith("/admin") or path.startswith("/padosi-admin")):
            return self.get_response(request)

        # Allow auth endpoints without session or permissions
        if path in ["/admin", "/admin/login", "/admin/login/post", "/admin/logout"]:
            return self.get_response(request)

        from apps.admin_panel.auth import _get_admin_from_session
        from apps.admin_panel.models.admin_auth import Admin

        admin_id = _get_admin_from_session(request)
        if not admin_id:
            import logging

            logging.getLogger(__name__).warning(
                f"Unauthorized admin access from path: {request.path}"
            )
            # For AJAX / JSON requests, return a clean 403 JSON — never add flash messages
            # that would leak into the agent login page after logout.
            is_ajax = (
                request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or "application/json" in request.headers.get("Accept", "")
                or request.content_type == "application/json"
            )
            if is_ajax:
                from django.http import JsonResponse

                return JsonResponse(
                    {
                        "success": False,
                        "message": "Unauthorized. Please sign in to the admin panel.",
                    },
                    status=403,
                )
            portal_error(
                request, "Please sign in to access the admin panel.", PORTAL_ADMIN
            )
            return redirect("admin_login_page")

        try:
            admin = Admin.objects.get(pk=admin_id)
        except Admin.DoesNotExist:
            from apps.admin_panel.views.dashboard import admin_logout

            is_ajax = (
                request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or "application/json" in request.headers.get("Accept", "")
                or request.content_type == "application/json"
            )
            if is_ajax:
                from django.http import JsonResponse

                return JsonResponse(
                    {"success": False, "message": "Admin account not found."},
                    status=403,
                )
            portal_error(request, "Admin account not found. Logged out.", PORTAL_ADMIN)
            return admin_logout(request)

        # Super admins have full access to everything
        if admin.role == "super":
            request.admin_user = admin
            return self.get_response(request)

        # Helper to redirect to first allowed route or log out
        def get_redirect_response(message):
            allowed_route = self.get_first_allowed_route(admin)
            if allowed_route:
                try:
                    from django.urls import reverse

                    url = reverse(allowed_route)
                    portal_error(request, message, PORTAL_ADMIN)
                    return redirect(url)
                except Exception:
                    pass
            from apps.admin_panel.views.dashboard import admin_logout

            portal_error(
                request,
                "Your staff account has no access permissions. Logged out.",
                PORTAL_ADMIN,
            )
            return admin_logout(request)

        # 1. DELETE ACTION PROTECTION:
        # Staff admins can never delete records.
        try:
            from django.urls import resolve

            url_name = resolve(request.path_info).url_name
        except Exception:
            url_name = ""
        is_delete_request = (
            request.method == "DELETE"
            or "delete" in url_name.lower()
            or "destroy" in url_name.lower()
            or "delete" in request.path.lower()
        )

        if is_delete_request:
            if request.headers.get(
                "accept"
            ) == "application/json" or request.path.startswith("/api/"):
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Unauthorized. Staff accounts do not have delete permissions.",
                    },
                    status=403,
                )
            return get_redirect_response(
                "Unauthorized. Staff accounts do not have delete permissions."
            )

        # 2. ADMIN USER / STAFF MANAGEMENT PROTECTION:
        # Staff admins can never access admin management routes.
        if (
            url_name.startswith("admin_admins")
            or url_name.startswith("admin_staff")
            or "/admin/admins/" in request.path
            or "/admin/staff/" in request.path
        ):
            if request.headers.get(
                "accept"
            ) == "application/json" or request.path.startswith("/api/"):
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Unauthorized. Only Super Admins can manage administrator accounts.",
                    },
                    status=403,
                )
            return get_redirect_response(
                "Unauthorized. Only Super Admins can manage administrator accounts."
            )

        # 3. SECTION/MODULE PERMISSION CHECK (exact lookup, deny-by-default):
        # get_required_permission() does a direct dict lookup — no prefix matching.
        # If url_name is a non-empty string not in the map, staff admins are denied.
        # If url_name is empty (resolver_match is None → genuine 404), pass through.
        required_permission = self.get_required_permission(url_name)
        if required_permission is None:
            if url_name:
                # Known URL pattern but not in our permission map → deny by default.
                if request.headers.get(
                    "accept"
                ) == "application/json" or request.path.startswith("/api/"):
                    return JsonResponse(
                        {
                            "success": False,
                            "message": "Unauthorized. Access to this section is not permitted for your staff account.",
                        },
                        status=403,
                    )
                return get_redirect_response(
                    "Access to this section is not permitted for your staff account."
                )
            # url_name is empty → unresolved URL; let Django render the 404.
            return self.get_response(request)

        permissions_list = (
            admin.permissions if isinstance(admin.permissions, list) else []
        )

        def _has(perm):
            if perm == "approvals":
                return (
                    "approvals_awaiting_verification" in permissions_list
                    or "approvals_missing_licenses" in permissions_list
                )
            return perm in permissions_list

        # A route may accept several permissions (tuple): any one is enough.
        required_any = (
            required_permission
            if isinstance(required_permission, tuple)
            else (required_permission,)
        )
        has_permission = any(_has(perm) for perm in required_any)
        required_permission = required_any[0]

        if not has_permission:
            if request.headers.get(
                "accept"
            ) == "application/json" or request.path.startswith("/api/"):
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Unauthorized. You do not have permission to access this module.",
                    },
                    status=403,
                )
            perm_name = required_permission.replace("_", " ").title()
            return get_redirect_response(
                f"Unauthorized. You do not have permission to access the {perm_name} module."
            )

        request.admin_user = admin
        return self.get_response(request)

    def get_required_permission(self, url_name):
        """Permission key(s) for an exact url_name, or None (= Super Admin only).

        The map lives in apps/admin_panel/registry.py (ROUTE_PERMISSIONS).
        """
        return registry.required_permission(url_name)

    def get_first_allowed_route(self, admin):
        permissions = admin.permissions if isinstance(admin.permissions, list) else []
        return registry.landing_route(permissions)
