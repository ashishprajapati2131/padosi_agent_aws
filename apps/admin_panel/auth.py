"""Admin panel session authentication (custom user_sessions tables, not Django auth).

Single home for resolving the admin of a request. views.dashboard re-exports these names
for backward compatibility; new code should import from here.
"""
import logging
from datetime import datetime

from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)

ADMIN_SESSION_COOKIE = "session_token"
# Admin logins last 7 days (was 30): a stolen admin cookie stays useful for less
# time. Sessions created before this change keep their original expiry.
ADMIN_SESSION_DAYS = 7


# ---------------------------------------------------------------------------
# Session Authentication Helper
# ---------------------------------------------------------------------------

def _admin_cookie_secure():
    return (not settings.DEBUG) or bool(getattr(settings, "SESSION_COOKIE_SECURE", False))


def invalidate_admin_session_token(token):
    """Delete the user_sessions / user_session_data rows for a session token."""
    if not token:
        return
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM user_sessions WHERE session_token = %s LIMIT 1",
                [token],
            )
            row = cursor.fetchone()
            if row:
                session_id = row[0]
                cursor.execute(
                    "DELETE FROM user_session_data WHERE session_id = %s",
                    [session_id],
                )
                cursor.execute(
                    "DELETE FROM user_sessions WHERE id = %s",
                    [session_id],
                )
    except Exception as exc:
        logger.error("Admin session cleanup error: %s", exc)


def clear_admin_session(request, response=None):
    """Invalidate the admin DB session and optionally delete the browser cookie."""
    token = request.COOKIES.get(ADMIN_SESSION_COOKIE)
    invalidate_admin_session_token(token)
    if response is not None:
        response.delete_cookie(ADMIN_SESSION_COOKIE)
    return response


def _get_admin_from_session(request):
    """Admin id for this request's session cookie, resolved once per request.

    Middleware (threat monitor, RBAC), the view and the context processor all ask;
    each call used to re-run the session queries (~7-10 per admin page).
    """
    token = request.COOKIES.get("session_token")
    cached = getattr(request, "_admin_session_cache", None)
    if cached is not None and cached[0] == token:
        return cached[1]
    admin_id = _resolve_admin_from_session(request)
    try:
        request._admin_session_cache = (token, admin_id)
    except AttributeError:
        pass  # some test doubles don't take attributes
    return admin_id


def _resolve_admin_from_session(request):
    r"""
    Validate the admin session from the session_token cookie.

    Checks:
      1. session_token cookie present
      2. Matching record exists in user_sessions
      3. Session has not expired (expires_at > UTC now)
      4. admin_id stored in user_session_data

    Returns the admin_id (int) if valid, else None.

    Laravel equivalent: App\Http\Middleware\AdminMiddleware (auth guard 'admin').
    """
    token = request.COOKIES.get("session_token")
    if not token:
        return None

    now_curr = datetime.now()

    try:
        with connection.cursor() as cursor:
            # Validate token against user_sessions and fetch last_activity
            cursor.execute(
                """
                SELECT id, last_activity
                FROM user_sessions
                WHERE session_token = %s
                  AND expires_at > %s
                LIMIT 1
                """,
                [token, now_curr],
            )
            row = cursor.fetchone()
            if not row:
                return None

            session_id = row[0]
            last_activity = row[1]

            # Throttled update of last_activity: at most once every 2 minutes
            try:
                from datetime import datetime as dt
                if isinstance(last_activity, str):
                    try:
                        last_act_dt = dt.fromisoformat(last_activity.replace(" ", "T"))
                    except Exception:
                        last_act_dt = None
                else:
                    last_act_dt = last_activity

                if not last_act_dt or (now_curr - last_act_dt).total_seconds() > 120:
                    cursor.execute(
                        "UPDATE user_sessions SET last_activity = %s WHERE id = %s",
                        [now_curr, session_id],
                    )
            except Exception:
                pass

            # Retrieve admin_id from user_session_data
            # Column names match actual schema: data_key / data_value
            cursor.execute(
                """
                SELECT data_value
                FROM user_session_data
                WHERE session_id = %s
                  AND data_key = 'admin_id'
                LIMIT 1
                """,
                [session_id],
            )
            data_row = cursor.fetchone()
            if not data_row:
                return None

            return int(data_row[0])

    except Exception as exc:
        logger.error("Session validation error: %s", exc)
        return None


def is_super_admin(admin_id):
    """True if the admin row has role 'super'."""
    from apps.admin_panel.models.admin_auth import Admin

    admin = Admin.objects.filter(id=admin_id).only("role").first()
    return bool(admin and admin.role == "super")
