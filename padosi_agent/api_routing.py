"""
Which /api/* requests go to FastAPI and which stay in Django.

FastAPI is mounted at /api, but a few Django views also live under /api/.
Those must reach Django, or FastAPI answers {"detail": "Not Found"}.
Shared by passenger_wsgi.py and padosi_agent/asgi.py so the two entry points
cannot drift apart again (c5842b6 silently undid 762dac2's fix).

When you add a Django URL under api/, add its prefix here.
"""

DJANGO_API_PREFIXES = (
    "/api/save-location/",
    "/api/facebook/",
    "/api/pincode/check-agents/",
)


def is_fastapi_path(path):
    if path != "/api" and not path.startswith("/api/"):
        return False
    return not path.startswith(DJANGO_API_PREFIXES)
