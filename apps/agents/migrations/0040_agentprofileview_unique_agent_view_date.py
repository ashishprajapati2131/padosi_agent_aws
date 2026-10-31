from django.db import migrations
from django.db.models import Count, Min, Sum


def merge_duplicate_profile_views(apps, schema_editor):
    """Fold duplicate (agent, view_date) rows into the lowest id so the unique index can be added.

    Concurrent first views used to insert duplicates; summing keeps the daily total unchanged.
    """
    AgentProfileView = apps.get_model('agents', 'AgentProfileView')
    duplicates = list(
        AgentProfileView.objects.values('agent_id', 'view_date')
        .annotate(rows=Count('id'), total=Sum('view_count'), keep_id=Min('id'))
        .filter(rows__gt=1)
    )
    for dup in duplicates:
        AgentProfileView.objects.filter(pk=dup['keep_id']).update(view_count=dup['total'])
        AgentProfileView.objects.filter(
            agent_id=dup['agent_id'], view_date=dup['view_date']
        ).exclude(pk=dup['keep_id']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0039_alter_agent_profession'),
    ]

    operations = [
        # Reverse is a no-op: merged rows keep the same total count.
        migrations.RunPython(merge_duplicate_profile_views, migrations.RunPython.noop),
        migrations.AlterUniqueTogether(
            name='agentprofileview',
            unique_together={('agent', 'view_date')},
        ),
    ]
