from django.db import migrations
from django.db.models import Q


def fix_mumbai_state(apps, schema_editor):
    City = apps.get_model('agents', 'City')
    City.objects.filter(slug__iexact='mumbai').exclude(state__iexact='Maharashtra').update(
        state='Maharashtra'
    )
    City.objects.filter(name__iexact='Mumbai').filter(
        Q(state__isnull=True) | Q(state='') | Q(state__iexact='Gujarat')
    ).update(state='Maharashtra')


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0041_add_agent_to_agentnotification'),
    ]

    operations = [
        migrations.RunPython(fix_mumbai_state, reverse_noop),
    ]
