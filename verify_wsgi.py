import os
import sys
from pathlib import Path
import json

# Setup
PROJECT_ROOT = Path(r"c:\Users\DELL\Downloads\7_22_2026\src")
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "padosi_agent.settings")

from django.core.wsgi import get_wsgi_application
django_wsgi_app = get_wsgi_application()

import fastapi_app as app_module
sys.modules['app'] = app_module
from a2wsgi import WSGIMiddleware
from fastapi_app.main import app as fastapi_application
fastapi_wsgi_app = WSGIMiddleware(fastapi_application)

def application(environ, start_response):
    path_info = environ.get('PATH_INFO', '')
    if path_info.startswith('/api'):
        environ['SCRIPT_NAME'] = environ.get('SCRIPT_NAME', '') + '/api'
        environ['PATH_INFO'] = path_info[4:]
        if not environ['PATH_INFO']:
            environ['PATH_INFO'] = '/'
        return fastapi_wsgi_app(environ, start_response)
    return django_wsgi_app(environ, start_response)

# Fake WSGI Request
def start_response(status, headers):
    print("STATUS:", status)
    print("HEADERS:", headers)

environ = {
    'REQUEST_METHOD': 'GET',
    'PATH_INFO': '/api/docs',
    'SCRIPT_NAME': '',
    'SERVER_NAME': 'localhost',
    'SERVER_PORT': '8000',
    'wsgi.url_scheme': 'http',
    'wsgi.input': open(os.devnull, 'rb')
}

print("Running WSGI...")
response = application(environ, start_response)
for chunk in response:
    print(chunk)
