from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0031_planupgradehandoff'),
    ]

    operations = [
        migrations.CreateModel(
            name='AgentPlanOffer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scratched_starter', models.BooleanField(default=False)),
                ('scratched_professional', models.BooleanField(default=False)),
                ('followed_platforms', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                # db_constraint=False: production's legacy agents.id type cannot
                # take a Django FK (MariaDB errno 150), like the other Agent FKs.
                ('agent', models.OneToOneField(db_constraint=False, on_delete=django.db.models.deletion.CASCADE, related_name='plan_offer', to='agents.agent')),
            ],
            options={
                'db_table': 'agent_plan_offers',
            },
        ),
    ]
