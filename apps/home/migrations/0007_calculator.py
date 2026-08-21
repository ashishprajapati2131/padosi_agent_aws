from django.db import migrations, models


def seed_calculator_catalog(apps, schema_editor):
    # Rows are seeded in 0008 after CalculatorCategory exists.
    pass


def unseed_calculator_catalog(apps, schema_editor):
    Calculator = apps.get_model('home', 'Calculator')
    Calculator.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0006_alter_blacklistedagent_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='Calculator',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=64, unique=True)),
                ('title', models.CharField(max_length=255)),
                ('short_description', models.TextField(blank=True, default='')),
                ('category', models.CharField(choices=[('investment', 'Mutual Funds & Investment'), ('savings', 'Savings'), ('loans', 'Loans & EMI'), ('retirement', 'Retirement Planning'), ('insurance', 'Insurance'), ('planning', 'Goal Planning'), ('tax', 'Tax')], default='investment', max_length=32)),
                ('icon_class', models.CharField(default='fa-solid fa-calculator', max_length=80)),
                ('is_active', models.BooleanField(default=False)),
                ('engine_ready', models.BooleanField(default=False)),
                ('sort_order', models.IntegerField(default=0)),
                ('meta_title', models.CharField(blank=True, default='', max_length=255)),
                ('meta_description', models.TextField(blank=True, default='')),
                ('disclaimer', models.TextField(blank=True, default='')),
                ('cta_text', models.CharField(default='Find a PadosiAgent', max_length=120)),
                ('cta_url', models.CharField(default='/find-agents/?openFilter=1', max_length=255)),
                ('default_inputs', models.JSONField(blank=True, default=dict)),
                ('faq_json', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'calculators',
                'ordering': ['sort_order', 'title'],
            },
        ),
        migrations.RunPython(seed_calculator_catalog, unseed_calculator_catalog),
    ]
