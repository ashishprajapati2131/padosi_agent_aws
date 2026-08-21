from django.db import migrations, models
import django.db.models.deletion


def seed_categories_and_remap(apps, schema_editor):
    Calculator = apps.get_model('home', 'Calculator')
    CalculatorCategory = apps.get_model('home', 'CalculatorCategory')
    from apps.home.calculators.registry import DEFAULT_CATEGORIES, SLUG_REDIRECTS
    from apps.home.calculators.seed import seed_calculators

    for spec in DEFAULT_CATEGORIES:
        CalculatorCategory.objects.get_or_create(
            slug=spec['slug'],
            defaults={
                'name': spec['name'],
                'icon_class': spec['icon_class'],
                'is_active': spec.get('is_active', True),
                'sort_order': spec['sort_order'],
                'meta_title': spec.get('meta_title', ''),
                'meta_description': spec.get('meta_description', ''),
            },
        )

    cats = {c.slug: c for c in CalculatorCategory.objects.all()}
    fallback = cats.get('planning') or next(iter(cats.values()))
    for calc in Calculator.objects.all():
        key = calc.category_legacy if hasattr(calc, 'category_legacy') else None
        calc.category = cats.get(key) or fallback
        calc.save(update_fields=['category'])

    for old, new in SLUG_REDIRECTS.items():
        if Calculator.objects.filter(slug=old).exists() and not Calculator.objects.filter(slug=new).exists():
            Calculator.objects.filter(slug=old).update(slug=new)

    seed_calculators(Calculator, CalculatorCategory)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0007_calculator'),
    ]

    operations = [
        migrations.CreateModel(
            name='CalculatorCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80)),
                ('slug', models.SlugField(max_length=64, unique=True)),
                ('icon_class', models.CharField(default='fa-solid fa-folder', max_length=80)),
                ('is_active', models.BooleanField(default=True)),
                ('sort_order', models.IntegerField(default=0)),
                ('meta_title', models.CharField(blank=True, default='', max_length=255)),
                ('meta_description', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name_plural': 'calculator categories',
                'db_table': 'calculator_categories',
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.RenameField(
            model_name='calculator',
            old_name='category',
            new_name='category_legacy',
        ),
        migrations.AddField(
            model_name='calculator',
            name='category',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='calculators',
                to='home.calculatorcategory',
            ),
        ),
        migrations.AlterField(
            model_name='calculator',
            name='slug',
            field=models.SlugField(max_length=80, unique=True),
        ),
        migrations.RunPython(seed_categories_and_remap, noop),
        migrations.RemoveField(
            model_name='calculator',
            name='category_legacy',
        ),
        migrations.AlterField(
            model_name='calculator',
            name='category',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='calculators',
                to='home.calculatorcategory',
            ),
        ),
    ]
