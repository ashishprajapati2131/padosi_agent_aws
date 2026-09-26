from django.db import models


class AdminBroadcast(models.Model):
    subject = models.CharField(max_length=255)
    message = models.TextField()
    target = models.CharField(max_length=50)
    channels = models.CharField(max_length=255)
    sent_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'admin_broadcasts'
        managed = True

    def __str__(self):
        return f"{self.subject} ({self.target})"
