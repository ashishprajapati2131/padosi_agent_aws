from django.db import models

class UserSession(models.Model):
    session_token = models.CharField(max_length=255, unique=True)
    admin_id = models.IntegerField(blank=True, null=True)
    agent_id = models.IntegerField(blank=True, null=True)
    distributor_id = models.IntegerField(blank=True, null=True)
    ip_address = models.CharField(blank=True, max_length=45, null=True)
    user_agent = models.CharField(blank=True, max_length=255, null=True)
    last_activity = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'user_sessions'


class UserSessionData(models.Model):
    data_key = models.CharField(max_length=255)
    data_value = models.TextField()
    created_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    session = models.ForeignKey(UserSession, db_column='session_id', on_delete=models.CASCADE)

    class Meta:
        db_table = 'user_session_data'
