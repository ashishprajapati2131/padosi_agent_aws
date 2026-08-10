from apps.agents.models import AgentNotification, FavoriteAgent, EventRegistration, Participant
from django.db import connection
c = connection.cursor()
c.execute('SHOW COLUMNS FROM participants')
cols = [r[0] for r in c.fetchall()]
print('participants has facebook cols:', 'facebook_access_token' in cols, 'status' in cols)
print('models OK:', AgentNotification._meta.db_table, FavoriteAgent._meta.db_table, EventRegistration._meta.db_table, Participant._meta.db_table)
