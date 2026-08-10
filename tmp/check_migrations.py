from django.contrib.auth import get_user_model
from apps.agents.models import Agent

User = get_user_model()

email = 'sanjay83insurance@gmail.com'

print('=== Django User record ===')
try:
    user = User.objects.get(email=email)
    print('  id         : %s' % user.id)
    print('  email      : %s' % user.email)
    print('  is_active  : %s' % user.is_active)
    print('  is_staff   : %s' % user.is_staff)
    print('  role       : %s' % getattr(user, 'role', 'N/A'))
    # print all fields
    for f in user._meta.fields:
        print('  %-20s: %s' % (f.name, getattr(user, f.name)))
except User.DoesNotExist:
    print('  NOT FOUND in auth user table')

print()
print('=== Agent record ===')
try:
    agent = Agent.objects.get(user__email=email)
    print('  agent.id   : %s' % agent.id)
    print('  fullname   : %s' % agent.fullname)
    print('  status     : %s' % agent.status)
    print('  is_approved: %s' % agent.is_approved)
except Agent.DoesNotExist:
    print('  NOT FOUND in agents table')
except Agent.MultipleObjectsReturned:
    agents = Agent.objects.filter(user__email=email)
    for a in agents:
        print('  agent.id=%s  status=%s  is_approved=%s' % (a.id, a.status, a.is_approved))

print()
print('=== Raw user table role column ===')
from django.db import connection
cursor = connection.cursor()
cursor.execute("SELECT id, email, role FROM users WHERE email = %s", [email])
rows = cursor.fetchall()
for r in rows:
    print('  id=%s  email=%s  role=%r' % r)
