# Generated manually for review — DO NOT run until explicitly confirmed.
#
# Adds a single nullable VARCHAR(50) column `suggestion_key` to
# `agent_career_timelines`. All existing rows receive NULL (no data change).
# A DB index is created on the column for fast de-duplication queries.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # Last applied migration in this app
        ('agents', '0012_agentbackup_agent_google_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='agentcareertimeline',
            name='suggestion_key',
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=50,
                null=True,
                help_text=(
                    'Stable key linking this row to an auto-detected suggestion. '
                    'NULL for all manually-created entries.'
                ),
            ),
        ),
    ]
