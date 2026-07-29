import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'padosi_agent.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth.models import User
from apps.insurance.views.agents import agents_index

request = RequestFactory().get('/insurance/agents/')
request.user = User.objects.get(username='manager@gmail.com')

try:
    response = agents_index(request)
    print("Status code:", response.status_code)
    # response.render() might not exist if it's an HttpResponse directly, so we check content
    content = response.content
    print("Render successful.")
except Exception as e:
    import traceback
    traceback.print_exc()
