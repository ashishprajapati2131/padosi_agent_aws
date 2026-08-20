"""
ASGI config for padosi_agent with FastAPI mounted on /api.
"""

import logging
import os
import sys

from django.core.asgi import get_asgi_application
from starlette.applications import Starlette
from starlette.routing import Mount

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "padosi_agent.settings")

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

django_application = get_asgi_application()

try:
    from fastapi_app.main import app as fastapi_application

    application = Starlette(
        routes=[
            Mount("/api", app=fastapi_application),
            Mount("/", app=django_application),
        ]
    )
except Exception:
    logger.exception("FastAPI application could not be loaded; serving Django only")
    application = django_application
