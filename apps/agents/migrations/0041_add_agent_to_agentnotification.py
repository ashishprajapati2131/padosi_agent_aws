from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0040_agentprofileview_unique_agent_view_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='agentnotification',
            name='agent',
            field=models.ForeignKey(
                db_column='agent_id',
                db_constraint=False,
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='notifications',
                to='agents.agent',
            ),
            preserve_default=False,
        ),
    ]

