import logging
from django.http import JsonResponse, HttpResponseRedirect
from django.middleware.csrf import get_token
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme

logger = logging.getLogger(__name__)


def csrf_failure_view(request, reason=""):
    """
    Custom CSRF Failure View.
    Ensures end clients NEVER get stuck on raw 403 Forbidden pages due to expired/stale CSRF cookies or long idle times.

    - For AJAX / API / JSON requests: Returns a clean JSON 403 response with a fresh CSRF token so JS can auto-retry.
    - For HTML Form submissions: Sets a fresh CSRF cookie, adds a user-friendly toast message, and redirects back seamlessly.
    """
    logger.warning(
        f"CSRF Validation Failure for client IP {request.META.get('REMOTE_ADDR')}: {reason} at {request.path}"
    )

    # 1. Force generate a brand new fresh CSRF token for the client
    fresh_token = get_token(request)
    is_secure = request.is_secure()

    is_ajax = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
        or request.content_type == "application/json"
        or request.path.startswith("/api/")
    )

    if is_ajax:
        response = JsonResponse(
            {
                "success": False,
                "csrf_error": True,
                "csrf_token": fresh_token,
                "message": "Your security session was refreshed. Please try submitting again.",
            },
            status=403,
        )
        # Ensure fresh token is set in response cookie
        response.set_cookie(
            "padosi_csrf_token", fresh_token, path="/", samesite="Lax", secure=is_secure
        )
        return response

    # Standard HTML Form Submission handling
    messages.warning(
        request,
        "Your security session timed out due to inactivity. We have refreshed your security token — please try submitting your form again.",
    )

    referer = request.META.get("HTTP_REFERER")
    allowed_hosts = {request.get_host()}
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts=allowed_hosts, require_https=is_secure
    ):
        redirect_url = referer
    else:
        redirect_url = request.path or "/"

    response = HttpResponseRedirect(redirect_url)
    response.set_cookie(
        "padosi_csrf_token", fresh_token, path="/", samesite="Lax", secure=is_secure
    )
    return response


def csrf_refresh_api(request):
    """
    Lightweight API endpoint for client-side JS to fetch a fresh CSRF token on-demand.
    """
    fresh_token = get_token(request)
    response = JsonResponse({"success": True, "csrf_token": fresh_token})
    response.set_cookie(
        "padosi_csrf_token",
        fresh_token,
        path="/",
        samesite="Lax",
        secure=request.is_secure(),
    )
    return response


def health_check_view(request):
    """
    Production health check endpoint for uptime monitors, reverse proxies, and load balancers.
    Checks DB connectivity and cache health.
    Returns HTTP 200 with status info, or HTTP 503 if database connection fails.
    """
    # Also served as /health/ready. Error text stays in the log: the driver's
    # message can carry the DB host and user, and this endpoint is public.
    db_ok = _db_ok()
    return _health_json(
        {
            "status": "healthy" if db_ok else "unhealthy",
            "database": "ok" if db_ok else "error",
            "cache": "ok" if _cache_ok() else "degraded",
        },
        ok=db_ok,
    )


DB_HEALTH_CACHE_KEY = "health:db"


def _health_json(data, ok=True):
    response = JsonResponse(data, status=200 if ok else 503)
    response["Cache-Control"] = "no-store"
    return response


def _db_ok():
    """SELECT 1, with the outcome kept 10s so a public probe cannot hammer MySQL.

    Connecting is bounded by DB_CONNECT_TIMEOUT (settings.DATABASES OPTIONS).
    """
    from django.core.cache import cache
    from django.db import connection

    try:
        cached = cache.get(DB_HEALTH_CACHE_KEY)
    except Exception:
        cached = None
    if cached is not None:
        return cached
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
        ok = bool(row and row[0] == 1)
    except Exception:
        logger.exception("[health] database check failed")
        ok = False
    try:
        cache.set(DB_HEALTH_CACHE_KEY, ok, timeout=10)
    except Exception:
        pass
    return ok


def _cache_ok():
    from django.core.cache import cache

    try:
        cache.set("__health_probe__", "ok", timeout=10)
        return cache.get("__health_probe__") == "ok"
    except Exception:
        logger.exception("[health] cache check failed")
        return False


def health_live_view(request):
    """Liveness: the app process answers. Touches neither the database nor the cache."""
    return _health_json({"status": "ok"})


def health_database_view(request):
    ok = _db_ok()
    return _health_json({"status": "ok" if ok else "unavailable"}, ok=ok)


def health_redis_view(request):
    from django.conf import settings

    if not getattr(settings, "REDIS_URL", ""):
        return _health_json({"status": "not_configured"})
    ok = _cache_ok()  # the default cache is Redis whenever REDIS_URL is set
    return _health_json({"status": "ok" if ok else "unavailable"}, ok=ok)
