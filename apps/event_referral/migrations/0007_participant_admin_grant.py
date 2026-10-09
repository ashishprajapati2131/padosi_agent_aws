from django.db import connection, migrations, models


def _column_exists(schema_editor, table, column):
    with schema_editor.connection.cursor() as cursor:
        try:
            names = {
                col.name
                for col in connection.introspection.get_table_description(cursor, table)
            }
            return column in names
        except Exception:
            return False


def add_grant_columns(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        if not _column_exists(schema_editor, 'event_referral_participants', 'grant_plan_slug'):
            ddl = "VARCHAR(50) NOT NULL DEFAULT ''"
            cursor.execute(
                f'ALTER TABLE event_referral_participants ADD COLUMN grant_plan_slug {ddl}',
            )
        if not _column_exists(schema_editor, 'event_referral_participants', 'grant_expires_at'):
            ddl = 'DATETIME NULL'
            cursor.execute(
                f'ALTER TABLE event_referral_participants ADD COLUMN grant_expires_at {ddl}',
            )
        if not _column_exists(schema_editor, 'event_referral_participants', 'grant_previous_plan'):
            ddl = "VARCHAR(50) NOT NULL DEFAULT ''"
            cursor.execute(
                f'ALTER TABLE event_referral_participants ADD COLUMN grant_previous_plan {ddl}',
            )


class Migration(migrations.Migration):

    dependencies = [
        ('event_referral', '0006_merge_0004_and_0005'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='eventreferralparticipant',
                    name='grant_plan_slug',
                    field=models.CharField(blank=True, default='', max_length=50),
                ),
                migrations.AddField(
                    model_name='eventreferralparticipant',
                    name='grant_expires_at',
                    field=models.DateTimeField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name='eventreferralparticipant',
                    name='grant_previous_plan',
                    field=models.CharField(blank=True, default='', max_length=50),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_grant_columns, migrations.RunPython.noop),
            ],
        ),
    ]
