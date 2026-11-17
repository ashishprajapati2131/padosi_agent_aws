# The localization tables were created with the MySQL server's default charset (not
# utf8mb4), so every Gujarati / Hindi / Tamil ... language name was stored as "?????"
# and the language switcher showed question marks. Convert the tables to utf8mb4 (same
# fix as wa_agent_bot 0007) and restore the seeded native names that were lost.

import importlib

from django.db import migrations, models

TABLES = (
    "localization_languages",
    "localization_state_languages",
    "localization_settings",
    "localization_user_preferences",
    "localization_content_translations",
    "localization_ui_translations",
)


def to_utf8mb4(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "mysql":
        return
    with connection.cursor() as cursor:
        for table in TABLES:
            cursor.execute(
                f"ALTER TABLE `{table}` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )


def restore_native_names(apps, schema_editor):
    """Re-write names that the old charset turned into '?' (admin-edited names are kept)."""
    seed = importlib.import_module(
        "apps.localization.migrations.0002_seed_languages_and_states"
    )
    SiteLanguage = apps.get_model("localization", "SiteLanguage")
    for code, native in seed.LANGUAGES:
        SiteLanguage.objects.filter(code=code, native_name__contains="?").update(
            native_name=native
        )


def forwards(apps, schema_editor):
    to_utf8mb4(apps, schema_editor)
    restore_native_names(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [
        ("localization", "0003_localizationsettings_enabled_uitranslation"),
    ]

    operations = [
        # 191 chars keeps the (language, msgid) unique index inside InnoDB's 767-byte
        # column limit once the column is 4-byte utf8mb4.
        migrations.AlterField(
            model_name="uitranslation",
            name="msgid",
            field=models.CharField(max_length=191),
        ),
        # Reverse is a no-op: converting back would turn the names into "?" again.
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
