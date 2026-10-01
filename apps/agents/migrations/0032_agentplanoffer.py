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
                ('agent', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='plan_offer', to='agents.agent')),
            ],
            options={
                'db_table': 'agent_plan_offers',
            },
        ),
    ]
