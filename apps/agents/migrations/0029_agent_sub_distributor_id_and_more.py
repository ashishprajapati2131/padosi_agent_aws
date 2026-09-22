from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0028_agentdraft_distributor_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='agentdraft',
            name='sub_distributor_id',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='agent',
            name='sub_distributor_id',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
