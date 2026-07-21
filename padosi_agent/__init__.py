# Monkey patch to bypass strict MariaDB/MySQL database version check in Django 6.x
from django.db.backends.base.base import BaseDatabaseWrapper
BaseDatabaseWrapper.check_database_version_supported = lambda self: None

# Fix for MariaDB < 10.5 syntax error with RETURNING in INSERT queries
from django.db.backends.mysql.features import DatabaseFeatures
DatabaseFeatures.can_return_columns_from_insert = property(
    lambda self: self.connection.maria_db_version >= (10, 5) if getattr(self.connection, 'is_mariadb', False) else False
)
DatabaseFeatures.can_return_rows_from_bulk_insert = property(
    lambda self: False
)

