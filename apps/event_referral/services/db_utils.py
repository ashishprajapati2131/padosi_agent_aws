"""MySQL connection recovery helpers for event_referral."""
from django.db import close_old_connections, connection
from django.db.utils import OperationalError

# 2006 / 2013: server has gone away; 2055: lost connection during query
_MYSQL_TRANSIENT_CODES = frozenset({2006, 2013, 2055, 4031})


def is_transient_mysql_error(exc):
    if not isinstance(exc, OperationalError):
        return False
    if exc.args and exc.args[0] in _MYSQL_TRANSIENT_CODES:
        return True
    message = str(exc).lower()
    return 'gone away' in message or 'lost connection' in message


def refresh_db_connection():
    close_old_connections()
    connection.close()
    connection.ensure_connection()


def run_with_db_retry(fn, *, attempts=3):
    last_exc = None
    for attempt in range(attempts):
        try:
            if attempt:
                refresh_db_connection()
            return fn()
        except OperationalError as exc:
            last_exc = exc
            if not is_transient_mysql_error(exc) or attempt + 1 >= attempts:
                raise
    if last_exc:
        raise last_exc
