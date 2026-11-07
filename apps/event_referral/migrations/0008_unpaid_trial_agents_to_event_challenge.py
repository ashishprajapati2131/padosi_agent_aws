from django.db import migrations


def move_unpaid_trial_agents_to_event_challenge(apps, schema_editor):
    Agent = apps.get_model('agents', 'Agent')
    EventReferralParticipant = apps.get_model('event_referral', 'EventReferralParticipant')
    AgentSubscription = apps.get_model('agents', 'AgentSubscription')

    trial_agent_ids = list(EventReferralParticipant.objects.filter(
        grant_expires_at__isnull=False
    ).values_list('agent_id', flat=True))

    paid_agent_ids = set(
        AgentSubscription.objects.filter(
            agent_id__in=trial_agent_ids,
            payment_status='completed'
        ).exclude(
            razorpay_payment_id__isnull=True,
            razorpay_order_id__isnull=True
        ).values_list('agent_id', flat=True)
    )

    unpaid_pending_ids = [
        aid for aid in trial_agent_ids
        if aid not in paid_agent_ids
    ]

    if unpaid_pending_ids:
        Agent.objects.filter(
            id__in=unpaid_pending_ids,
            status='pending_approval'
        ).update(status='event_challenge')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('event_referral', '0007_participant_admin_grant'),
        ('agents', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            move_unpaid_trial_agents_to_event_challenge,
            noop_reverse,
        ),
    ]
