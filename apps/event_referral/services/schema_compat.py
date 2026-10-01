"""Ensure event_referral metric columns exist (local DBs that lag on migrations)."""
import logging
import threading
import time

from django.core.cache import cache
from django.db import connection

from apps.event_referral.services.db_utils import is_transient_mysql_error, run_with_db_retry

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_ensured = False
_ensure_failed_until = 0.0
_ENSURE_FAIL_COOLDOWN_SEC = 30

_METRIC_COLUMNS = (
    (
        'event_referral_campaigns',
        'registration_link_open_count',
        'BIGINT UNSIGNED NOT NULL DEFAULT 0',
        'INTEGER NOT NULL DEFAULT 0',
    ),
    (
        'event_referral_participants',
        'page_active_seconds',
        'INT UNSIGNED NOT NULL DEFAULT 0',
        'INTEGER NOT NULL DEFAULT 0',
    ),
    (
        'event_referral_participants',
        'blocked_by_admin',
        'TINYINT(1) NOT NULL DEFAULT 0',
        'INTEGER NOT NULL DEFAULT 0',
    ),
)

_BLOCKED_BY_ADMIN_INDEX = (
    'event_referral_participants',
    'event_referral_participants_blocked_by_admin_idx',
    'blocked_by_admin',
)


def _table_columns(cursor, table):
    return {
        col.name
        for col in connection.introspection.get_table_description(cursor, table)
    }


def _column_exists(cursor, table, column):
    try:
        return column in _table_columns(cursor, table)
    except Exception:
        return False


def _index_exists_mysql(cursor, table, index_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND INDEX_NAME = %s
        """,
        [table, index_name],
    )
    return bool(cursor.fetchone()[0])


def _metrics_schema_complete(cursor):
    for table, column, _mysql_ddl, _sqlite_ddl in _METRIC_COLUMNS:
        if not _column_exists(cursor, table, column):
            return False
    return True


def _apply_missing_columns():
    vendor = connection.vendor
    with connection.cursor() as cursor:
        if _metrics_schema_complete(cursor):
            return

        for table, column, mysql_ddl, sqlite_ddl in _METRIC_COLUMNS:
            if _column_exists(cursor, table, column):
                continue
            ddl = mysql_ddl if vendor == 'mysql' else sqlite_ddl
            qn = connection.ops.quote_name
            cursor.execute(
                f'ALTER TABLE {qn(table)} ADD COLUMN {qn(column)} {ddl}',
            )
            logger.info('Event referral schema: added %s.%s', table, column)

        if vendor == 'mysql':
            table, index_name, column = _BLOCKED_BY_ADMIN_INDEX
            if _column_exists(cursor, table, column) and not _index_exists_mysql(
                cursor, table, index_name,
            ):
                cursor.execute(
                    f'CREATE INDEX `{index_name}` ON `{table}` (`{column}`)',
                )


def _clear_campaign_cache():
    try:
        cache.delete('current_event_referral_campaign')
    except Exception:
        pass


def ensure_event_referral_metrics_schema(*, log_errors=True):
    """
    Add registration_link_open_count / page_active_seconds / blocked_by_admin
    when migration 0005 has not been applied yet.
    """
    global _ensured, _ensure_failed_until
    if _ensured:
        return True
    if time.time() < _ensure_failed_until:
        return False

    with _lock:
        if _ensured:
            return True
        if time.time() < _ensure_failed_until:
            return False
        try:
            run_with_db_retry(_apply_missing_columns)
            _clear_campaign_cache()
            _ensured = True
            _ensure_failed_until = 0.0
            return True
        except Exception as exc:
            try:
                def _check_complete():
                    with connection.cursor() as cursor:
                        return _metrics_schema_complete(cursor)

                if run_with_db_retry(_check_complete):
                    _clear_campaign_cache()
                    _ensured = True
                    _ensure_failed_until = 0.0
                    return True
            except Exception:
                pass

            _ensure_failed_until = time.time() + _ENSURE_FAIL_COOLDOWN_SEC
            if log_errors:
                if is_transient_mysql_error(exc):
                    logger.warning(
                        'Event referral metrics schema ensure failed (transient MySQL): %s',
                        exc,
                    )
                else:
                    logger.exception('Event referral metrics schema ensure failed: %s', exc)
            return False
