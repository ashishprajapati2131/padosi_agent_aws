from django.db import migrations, models


STATUS_MAP = {
    'Started': 'quick_registered',
    'Completed': 'form_completed',
    'Abandoned': 'abandoned',
}


def forwards(apps, schema_editor):
    Lead = apps.get_model('admin_panel', 'RegistrationLead')
    keep_ids = set()
    seen_phones = set()
    for lead in Lead.objects.order_by('-updated_at', '-id').iterator():
        phone = (lead.phone or '').strip()
        mapped = STATUS_MAP.get(lead.status, lead.status)
        if mapped not in (
            'quick_registered',
            'form_started',
            'form_completed',
            'payment_completed',
            'converted',
            'abandoned',
        ):
            mapped = 'quick_registered'
        if phone in seen_phones:
            continue
        seen_phones.add(phone)
        keep_ids.add(lead.id)
        updates = {}
        if lead.status != mapped:
            updates['status'] = mapped
        form_filled = mapped in ('form_completed', 'payment_completed', 'converted')
        payment_status = 'completed' if mapped in ('payment_completed', 'converted') else 'none'
        if getattr(lead, 'form_filled', False) != form_filled:
            updates['form_filled'] = form_filled
        if getattr(lead, 'payment_status', 'none') != payment_status:
            updates['payment_status'] = payment_status
        if updates:
            Lead.objects.filter(pk=lead.id).update(**updates)
    Lead.objects.exclude(id__in=keep_ids).delete()


def backwards(apps, schema_editor):
    Lead = apps.get_model('admin_panel', 'RegistrationLead')
    reverse_map = {
        'quick_registered': 'Started',
        'form_started': 'Started',
        'form_completed': 'Completed',
        'payment_completed': 'Completed',
        'converted': 'Completed',
        'abandoned': 'Abandoned',
    }
    for lead in Lead.objects.all().iterator():
        mapped = reverse_map.get(lead.status, 'Started')
        Lead.objects.filter(pk=lead.id).update(status=mapped)


class Migration(migrations.Migration):

    dependencies = [
        ('admin_panel', '0014_registration_lead'),
    ]

    operations = [
        migrations.AddField(
            model_name='registrationlead',
            name='form_filled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='registrationlead',
            name='payment_status',
            field=models.CharField(choices=[('none', 'Not started'), ('pending', 'Pending'), ('completed', 'Completed'), ('failed', 'Failed')], db_index=True, default='none', max_length=20),
        ),
        migrations.AddField(
            model_name='registrationlead',
            name='converted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='registrationlead',
            name='status',
            field=models.CharField(choices=[('quick_registered', 'Quick Registered'), ('form_started', 'Form Started'), ('form_completed', 'Form Completed'), ('payment_completed', 'Payment Completed'), ('converted', 'Converted'), ('abandoned', 'Abandoned')], db_index=True, default='quick_registered', max_length=32),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name='registrationlead',
            name='phone',
            field=models.CharField(db_index=True, max_length=15, unique=True),
        ),
        migrations.AlterField(
            model_name='registrationlead',
            name='agent_id',
            field=models.IntegerField(blank=True, db_index=True, null=True),
        ),
    ]
