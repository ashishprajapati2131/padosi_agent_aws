"""
ASGI config for padosi_agent with FastAPI mounted on /api.
"""

import logging
import os
import sys

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "padosi_agent.settings")

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

django_application = get_asgi_application()
FASTAPI_PREFIXES = ("/api/v1", "/api/reset-password", "/api/docs", "/api/openapi.json", "/api/redoc")

try:
    from fastapi_app.main import app as fastapi_application

    async def application(scope, receive, send):
        if scope.get("type") in ("http", "websocket"):
            path = scope.get("path", "")
            if any(path.startswith(prefix) for prefix in FASTAPI_PREFIXES):
                await fastapi_application(scope, receive, send)
                return
        await django_application(scope, receive, send)
except Exception:
    logger.exception("FastAPI application could not be loaded; serving Django only")
    application = django_application


