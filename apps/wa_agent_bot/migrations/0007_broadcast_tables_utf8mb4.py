# The broadcast tables were created with the server's default charset (not utf8mb4),
# so MySQL stored every emoji in a broadcast message as "?". Convert them to utf8mb4.

from django.db import migrations

TABLES = ("wa_broadcasts", "wa_broadcast_recipients", "wa_bot_message_logs")


def to_utf8mb4(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "mysql":
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(
                f"ALTER TABLE `{table}` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )


class Migration(migrations.Migration):
    dependencies = [
        ("wa_agent_bot", "0006_wabroadcast_send_card_wabroadcastrecipient_image_url"),
    ]

    # Reverse is a no-op: converting back would turn stored emojis into "?" again.
    operations = [migrations.RunPython(to_utf8mb4, migrations.RunPython.noop)]
