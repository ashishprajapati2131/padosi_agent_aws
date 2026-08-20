import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

# cPanel virtualenv site-packages. Override with VENV_SITE_PACKAGES /
# VENV_SITE_PACKAGES_64 when the hosting path changes.
_DEFAULT_VENV = "/home/m69qf6gyhm3n/virtualenv/padosiagentdjango/src/3.11/lib/python3.11/site-packages"
_DEFAULT_VENV_64 = "/home/m69qf6gyhm3n/virtualenv/padosiagentdjango/src/3.11/lib64/python3.11/site-packages"
VENV_PATH = os.environ.get("VENV_SITE_PACKAGES", _DEFAULT_VENV)
VENV_PATH_64 = os.environ.get("VENV_SITE_PACKAGES_64", _DEFAULT_VENV_64)
if os.path.exists(VENV_PATH) and VENV_PATH not in sys.path:
    sys.path.insert(0, VENV_PATH)
if os.path.exists(VENV_PATH_64) and VENV_PATH_64 not in sys.path:
    sys.path.insert(0, VENV_PATH_64)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "padosi_agent.settings")

from django.core.wsgi import get_wsgi_application

django_wsgi_application = get_wsgi_application()

try:
    from a2wsgi import ASGIMiddleware
    from padosi_agent.asgi import application as asgi_app

    asgi_wsgi_application = ASGIMiddleware(asgi_app)
    FASTAPI_ENABLED = True
except Exception:
    import logging

    logging.getLogger(__name__).exception("ASGI/FastAPI could not be loaded in passenger_wsgi")
    FASTAPI_ENABLED = False


def application(environ, start_response):
    path = environ.get("PATH_INFO", "")
    if FASTAPI_ENABLED and path.startswith("/api"):
        return asgi_wsgi_application(environ, start_response)
    return django_wsgi_application(environ, start_response)
