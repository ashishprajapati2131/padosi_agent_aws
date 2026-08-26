import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# cPanel virtualenv site-packages. Add to sys.path FIRST before any 3rd party packages
_POSSIBLE_VENVS = [
    "/home/m69qf6gyhm3n/virtualenv/padosiagent_django/src/3.11/lib/python3.11/site-packages",
    "/home/m69qf6gyhm3n/virtualenv/padosiagent_django/src/3.11/lib64/python3.11/site-packages",
    "/home/m69qf6gyhm3n/virtualenv/padosiagentdjango/src/3.11/lib/python3.11/site-packages",
    "/home/m69qf6gyhm3n/virtualenv/padosiagentdjango/src/3.11/lib64/python3.11/site-packages",
]

for venv_dir in _POSSIBLE_VENVS:
    if os.path.exists(venv_dir) and venv_dir not in sys.path:
        sys.path.insert(0, venv_dir)

try:
    from dotenv import load_dotenv

    for env_path in [PROJECT_ROOT / ".env", PROJECT_ROOT.parent / ".env"]:
        if env_path.exists():
            load_dotenv(env_path)
            break
except ImportError:
    pass

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
