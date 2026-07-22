"""
ASGI config for padosiagent project with FastAPI mounted on /api.
"""

import os
import sys

from django.core.asgi import get_asgi_application
from starlette.applications import Starlette
from starlette.routing import Mount

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'padosi_agent.settings')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    import fastapi_app as app_module
    sys.modules['app'] = app_module
    from fastapi_app.main import app as fastapi_application
    FASTAPI_AVAILABLE = True
except Exception as e:
    print(f"Warning: Could not import FastAPI application: {e}")
    FASTAPI_AVAILABLE = False

django_application = get_asgi_application()

if FASTAPI_AVAILABLE:
    routes = [
        Mount("/api", app=fastapi_application),
        Mount("/", app=django_application),
    ]
    application = Starlette(routes=routes)
else:
    application = django_application

