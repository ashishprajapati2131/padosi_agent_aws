from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0041_add_agent_to_agentnotification'),
    ]

    operations = [
        migrations.AddField(
            model_name='agent',
            name='admin_restricted',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='agent',
            name='restricted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='agent',
            name='status_before_restriction',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
    ]
