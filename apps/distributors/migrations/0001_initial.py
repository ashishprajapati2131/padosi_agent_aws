from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='SubDistributor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('distributor_id', models.IntegerField(db_index=True, help_text='ID of parent distributor in users table')),
                ('fullname', models.CharField(max_length=191)),
                ('email', models.CharField(max_length=191, unique=True)),
                ('mobile', models.CharField(db_index=True, max_length=20)),
                ('password', models.CharField(max_length=255)),
                ('code', models.CharField(db_index=True, max_length=64, unique=True)),
                ('status', models.CharField(choices=[('active', 'Active'), ('suspended', 'Suspended'), ('inactive', 'Inactive')], default='active', max_length=20)),
                ('clicks', models.IntegerField(default=0)),
                ('notes', models.TextField(blank=True, default='')),
                ('last_login_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'sub_distributors',
                'ordering': ['-created_at'],
            },
        ),
    ]
