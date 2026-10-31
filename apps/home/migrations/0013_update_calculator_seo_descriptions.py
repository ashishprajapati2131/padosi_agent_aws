from django.db import migrations


def update_calculator_seo_descriptions(apps, schema_editor):
    Calculator = apps.get_model('home', 'Calculator')
    from apps.home.calculators.registry import CALCULATORS

    for spec in CALCULATORS:
        slug = spec.get('slug')
        meta_desc = spec.get('meta_description')
        if slug and meta_desc:
            Calculator.objects.filter(slug=slug).update(meta_description=meta_desc)


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0012_linkogsetting'),
    ]

    operations = [
        migrations.RunPython(update_calculator_seo_descriptions, reverse_noop),
    ]

