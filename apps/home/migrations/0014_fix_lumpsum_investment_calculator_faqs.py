from django.db import migrations


def sync_lumpsum_faqs(apps, schema_editor):
    Calculator = apps.get_model('home', 'Calculator')
    from apps.home.calculators.registry import get_spec

    for slug in ('lumpsum-calculator', 'investment-calculator'):
        spec = get_spec(slug)
        if not spec:
            continue
        faqs = spec.get('faqs') or []
        if faqs:
            Calculator.objects.filter(slug=slug).update(faq_json=faqs)


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0013_update_calculator_seo_descriptions'),
    ]

    operations = [
        migrations.RunPython(sync_lumpsum_faqs, reverse_noop),
    ]
