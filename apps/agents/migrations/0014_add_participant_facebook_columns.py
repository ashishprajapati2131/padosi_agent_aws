"""Add Facebook connection columns to the Laravel-owned participants table.

The participants table is created by the Laravel (PHP) schema and is mapped in
Django as a managed=False model (apps.agents.models.Participant). The Laravel
FacebookPostController writes facebook_access_token / status / facebook_post_id
etc., so we add these columns safely (idempotent, guarded per-column) here.

Run: python manage.py migrate agents
"""

from django.db import migrations

# column_name -> MySQL DDL snippet (full column definition)
PARTICIPANT_FB_COLUMNS = {
    'facebook_access_token': "`facebook_access_token` LONGTEXT NULL",
    'facebook_user_id': "`facebook_user_id` VARCHAR(191) NULL",
    'facebook_post_id': "`facebook_post_id` VARCHAR(191) NULL",
    'facebook_post_url': "`facebook_post_url` VARCHAR(500) NULL",
    'status': "`status` VARCHAR(50) NOT NULL DEFAULT 'registered'",
    'manual_share': "`manual_share` TINYINT(1) NOT NULL DEFAULT 0",
    'screenshot_path': "`screenshot_path` VARCHAR(500) NULL",
}


def add_participant_columns(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = 'participants'"
        )
        existing = {row[0] for row in cursor.fetchall()}
        for column, ddl in PARTICIPANT_FB_COLUMNS.items():
            if column in existing:
                continue
            cursor.execute(f"ALTER TABLE `participants` ADD COLUMN {ddl}")


def remove_participant_columns(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = 'participants'"
        )
        existing = {row[0] for row in cursor.fetchall()}
        for column in PARTICIPANT_FB_COLUMNS:
            if column in existing:
                cursor.execute(f"ALTER TABLE `participants` DROP COLUMN `{column}`")


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0013_agentprofile_show_claims_stats_and_more'),
    ]

    operations = [
        migrations.RunPython(add_participant_columns, remove_participant_columns),
    ]
