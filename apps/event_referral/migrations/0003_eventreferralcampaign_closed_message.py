from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('event_referral', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventreferralcampaign',
            name='closed_message',
            field=models.TextField(
                blank=True,
                default=(
                    'This registration link is deactivated for now. '
                    'Please wait until it opens again.'
                ),
            ),
        ),
    ]
