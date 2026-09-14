# Generated manually — creates registration_activity_logs table for event tracking.
# Note: The table is pre-created via raw SQL in the DB to avoid FK constraint issues
# with an unrelated existing migration. Use --fake on this migration.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0026_add_analytics_models'),
    ]

    operations = [
        migrations.CreateModel(
            name='RegistrationActivityLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('draft_id', models.IntegerField(blank=True, db_index=True, null=True)),
                ('subscription_id', models.IntegerField(blank=True, null=True)),
                ('event_name', models.CharField(db_index=True, max_length=64)),
                ('details', models.JSONField(blank=True, null=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('agent', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='registration_activity_logs', to='agents.agent')),
            ],
            options={
                'db_table': 'registration_activity_logs',
                'ordering': ['-created_at'],
                'managed': True,
            },
        ),
    ]
