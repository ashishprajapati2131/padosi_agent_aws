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


def _index_exists_mysql(cursor, table, index_name):
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND INDEX_NAME = %s
        """,
        [table, index_name],
    )
    return bool(cursor.fetchone()[0])


def add_metrics_columns(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if not _column_exists(schema_editor, 'event_referral_campaigns', 'registration_link_open_count'):
            ddl = (
                'BIGINT UNSIGNED NOT NULL DEFAULT 0'
                if vendor == 'mysql'
                else 'INTEGER NOT NULL DEFAULT 0'
            )
            cursor.execute(
                f'ALTER TABLE event_referral_campaigns ADD COLUMN registration_link_open_count {ddl}',
            )
        if not _column_exists(schema_editor, 'event_referral_participants', 'page_active_seconds'):
            ddl = (
                'INT UNSIGNED NOT NULL DEFAULT 0'
                if vendor == 'mysql'
                else 'INTEGER NOT NULL DEFAULT 0'
            )
            cursor.execute(
                f'ALTER TABLE event_referral_participants ADD COLUMN page_active_seconds {ddl}',
            )
        if not _column_exists(schema_editor, 'event_referral_participants', 'blocked_by_admin'):
            ddl = (
                'TINYINT(1) NOT NULL DEFAULT 0'
                if vendor == 'mysql'
                else 'INTEGER NOT NULL DEFAULT 0'
            )
            cursor.execute(
                f'ALTER TABLE event_referral_participants ADD COLUMN blocked_by_admin {ddl}',
            )
        if vendor == 'mysql' and _column_exists(
            schema_editor, 'event_referral_participants', 'blocked_by_admin',
        ) and not _index_exists_mysql(
            cursor, 'event_referral_participants', 'event_referral_participants_blocked_by_admin_idx',
        ):
            cursor.execute(
                """
                CREATE INDEX event_referral_participants_blocked_by_admin_idx
                ON event_referral_participants (blocked_by_admin)
                """,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('event_referral', '0003_eventreferralcampaign_closed_message'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='eventreferralcampaign',
                    name='registration_link_open_count',
                    field=models.PositiveBigIntegerField(default=0),
                ),
                migrations.AddField(
                    model_name='eventreferralparticipant',
                    name='page_active_seconds',
                    field=models.PositiveIntegerField(default=0),
                ),
                migrations.AddField(
                    model_name='eventreferralparticipant',
                    name='blocked_by_admin',
                    field=models.BooleanField(default=False, db_index=True),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_metrics_columns, migrations.RunPython.noop),
            ],
        ),
    ]
