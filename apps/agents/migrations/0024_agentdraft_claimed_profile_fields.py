from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0023_subscriptionplan_badge_text_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='agentdraft',
            name='slug',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='agentdraft',
            name='whatsapp',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='agentdraft',
            name='claims_settled',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='agentdraft',
            name='claim_amount',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
    ]
