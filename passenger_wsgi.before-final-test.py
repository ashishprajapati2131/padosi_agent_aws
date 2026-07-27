import os
import sys

sys.path.insert(
    0,
    "/home/m69qf6gyhm3n/padosiagentdjango/src"
)

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "padosi_agent.settings"
)

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
