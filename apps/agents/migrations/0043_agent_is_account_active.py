from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0042_move_models_from_admin_panel'),
    ]

    operations = [
        migrations.AddField(
            model_name='agent',
            name='is_account_active',
            field=models.BooleanField(default=True),
        ),
    ]
