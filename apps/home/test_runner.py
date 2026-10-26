from django.test.runner import DiscoverRunner, ParallelTestSuite, _init_worker
from django.conf import settings
from django.db import connections
from django.db.models.options import Options


def _configure_test_settings():
    """Swap DB to in-memory SQLite and cache to LocMem; force all models managed."""
    settings.TESTING = True
    settings.SECURE_SSL_REDIRECT = False
    settings.ALLOWED_HOSTS = ['*']
    db_config = dict(settings.DATABASES['default'])
    db_config['ENGINE'] = 'django.db.backends.sqlite3'
    db_config['NAME'] = ':memory:'
    
    if 'TEST' not in db_config or not isinstance(db_config['TEST'], dict):
        db_config['TEST'] = {}
    db_config['TEST']['NAME'] = ':memory:'
    
    settings.DATABASES['default'] = db_config
    # Update connections dictionary
    connections.databases['default'] = settings.DATABASES['default']
    
    # Force cache to in-memory LocMemCache during test execution so disk I/O, file locks, and Windows permission issues don't pollute or break tests
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'test-runner-cache',
        }
    }
    try:
        from django.core.cache import caches
        caches['default'] = caches.create_connection('default')
    except Exception:
        pass

    # Clear the cached connection instance if it was already initialized
    try:
        connections['default'].close()
        # Clear from the thread local _connections object
        if hasattr(connections._connections, 'default'):
            delattr(connections._connections, 'default')
    except Exception:
        pass

    # Force Options.managed to always return True for tests, with a dummy setter to avoid AttributeError
    Options.managed = property(fget=lambda self: True, fset=lambda self, value: None)


def _import_all_views():
    # Load every view module up front. A module first imported while a test patches a helper it
    # imports by name (e.g. _get_admin_from_session) would keep the mock for every later test.
    from django.urls import get_resolver
    get_resolver().url_patterns


def _worker_process_setup():
    # Spawned parallel workers (Windows/macOS) re-import settings, so redo the test swaps there too.
    _configure_test_settings()


def _init_worker_with_views(*args, **kwargs):
    _init_worker(*args, **kwargs)
    _import_all_views()


class _ParallelSuite(ParallelTestSuite):
    process_setup = _worker_process_setup
    init_worker = _init_worker_with_views


class ManagedModelsTestRunner(DiscoverRunner):
    """
    Test runner that forces all Django models to be managed = True during tests,
    and swaps the default database to an in-memory SQLite database to avoid MySQL-specific setup errors.
    Works with --parallel: forked workers inherit the swap, spawned workers redo it.
    """
    parallel_test_suite = _ParallelSuite

    def __init__(self, *args, **kwargs):
        _configure_test_settings()
        super().__init__(*args, **kwargs)

    def setup_test_environment(self, **kwargs):
        from django.apps import apps
        for model in apps.get_models():
            model._meta.managed = True
            
        super().setup_test_environment(**kwargs)
        _import_all_views()
