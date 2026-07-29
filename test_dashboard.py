import os
import django
import sys
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'padosi_agent.settings')
django.setup()

from django.test import RequestFactory
from apps.insurance.views.dashboard import dashboard
from django.contrib.auth.models import User
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware

try:
    user = User.objects.get(username="manager@gmail.com")
    
    factory = RequestFactory()
    request = factory.get('/insurance/dashboard/')
    request.user = user
    
    # Add session and messages
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    
    msg_middleware = MessageMiddleware(lambda r: None)
    msg_middleware.process_request(request)
    
    response = dashboard(request)
    print(f"Status code: {response.status_code}")
    if response.status_code == 302:
        print(f"Redirected to: {response.url}")
    elif response.status_code == 500:
        print(response.content)
    else:
        # If it returns 200, it's a TemplateResponse, we need to render it to catch template errors.
        response.render()
        print("Rendered successfully.")
except Exception as e:
    print("Caught Exception!")
    traceback.print_exc()
