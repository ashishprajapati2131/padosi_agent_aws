from django.db import migrations


def backfill(apps, schema_editor):
    """Winners granted before win_emailed_at existed were emailed in that same run.

    Without this, the next grant_paldi_trial --apply would email all of them again.
    """
    from datetime import datetime

    Participant = apps.get_model("event_referral", "EventReferralParticipant")
    Participant.objects.filter(status="won", win_emailed_at__isnull=True).update(
        win_emailed_at=datetime.now()
    )


class Migration(migrations.Migration):

    dependencies = [
        ("event_referral", "0010_eventreferralparticipant_win_emailed_at"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
