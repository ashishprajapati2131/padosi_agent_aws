# These tests need Django's runner (test database + ManagedModelsTestRunner).
# Plain pytest has no pytest-django here, so stop with the right command instead of 24 ImproperlyConfigured errors.
import pytest


def pytest_configure(config):
    if not config.pluginmanager.hasplugin("django"):
        pytest.exit(
            "Run admin panel tests with: python manage.py test apps.admin_panel",
            returncode=4,
        )
