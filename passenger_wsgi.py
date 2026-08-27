import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env
try:
    from dotenv import load_dotenv
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

# Python 3.11 Virtual Environment Site-Packages
_VENVS = [
    "/home/m69qf6gyhm3n/virtualenv/padosiagent_django/src/3.11/lib/python3.11/site-packages",
    "/home/m69qf6gyhm3n/virtualenv/padosiagent_django/src/3.11/lib64/python3.11/site-packages",
    "/home/m69qf6gyhm3n/virtualenv/padosiagentdjango/src/3.11/lib/python3.11/site-packages",
    "/home/m69qf6gyhm3n/virtualenv/padosiagentdjango/src/3.11/lib64/python3.11/site-packages",
]

for venv_dir in _VENVS:
    if os.path.exists(venv_dir) and venv_dir not in sys.path:
        sys.path.insert(0, venv_dir)

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
    logging.getLogger(__name__).exception("ASGI/FastAPI could not be loaded")
    FASTAPI_ENABLED = False

def application(environ, start_response):
    path = environ.get("PATH_INFO", "")
    if FASTAPI_ENABLED and path.startswith("/api"):
        return asgi_wsgi_application(environ, start_response)
    return django_wsgi_application(environ, start_response)
