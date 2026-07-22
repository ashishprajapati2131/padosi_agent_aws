# import os
# import sys
# from pathlib import Path

# # 1. પ્રોજેક્ટનો ચોક્કસ પાથ સેટ કરો
# PROJECT_ROOT = Path(__file__).resolve().parent
# sys.path.insert(0, str(PROJECT_ROOT))

# # 2. વર્ચ્યુઅલ એન્વાયરમેન્ટ (venv) ના પેકેજીસનો પાથ ઉમેરો
# # આ પાથ તમારા Django અને અન્ય મોડ્યુલ્સ શોધવામાં મદદ કરશે
# VENV_PACKAGES = '/home/m69qf6gyhm3n/virtualenv/padosiagentdjango/src/3.11/lib/python3.11/site-packages'
# if VENV_PACKAGES not in sys.path:
#     sys.path.insert(0, VENV_PACKAGES)


# # 3. .env ફાઇલને લોડ કરો
# try:
#     from dotenv import load_dotenv
#     env_path = PROJECT_ROOT / '.env'
#     if env_path.exists():
#         load_dotenv(env_path)
# except ImportError:
#     # જો dotenv ન મળે તો આ સ્ટેપ સ્કીપ થશે
#     pass

# # 4. Django Settings સેટ કરો
# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "padosi_agent.settings")

# # 5. WSGI Application લોડ કરો
# try:
#     from django.core.wsgi import get_wsgi_application
#     application = get_wsgi_application()
# except Exception as e:
#      def application(environ, start_response):
#         status = '500 Internal Server Error'
#         output = str(e).encode('utf-8')
#         response_headers = [('Content-type', 'text/plain'), ('Content-Length', str(len(output)))]
#         start_response(status, response_headers)
#         return [output]


import os
import sys
from pathlib import Path


# પ્રોજેક્ટનો ચોક્કસ પાથ સેટ કરો
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# .env ફાઇલને ફોર્સફુલી લોડ કરો (જો python-dotenv ઇન્સ્ટોલ હોય તો)
try:
    from dotenv import load_dotenv
    env_path = PROJECT_ROOT / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

# Set Django Settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "padosi_agent.settings")

# Try loading combined ASGI app via a2wsgi for cPanel Passenger
try:
    from a2wsgi import ASGIMiddleware
    from padosi_agent.asgi import application as asgi_app
    application = ASGIMiddleware(asgi_app)
except Exception as e:
    from django.core.wsgi import get_wsgi_application
    application = get_wsgi_application()




# import os
# import sys

# sys.path.insert(
#     0,
#     "/home/m69qf6gyhm3n/padosiagentdjango/src"
# )

# os.environ.setdefault(
#     "DJANGO_SETTINGS_MODULE",
#     "padosi_agent.settings"
# )

# from django.core.wsgi import get_wsgi_application

# application = get_wsgi_application()
