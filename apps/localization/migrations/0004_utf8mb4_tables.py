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
    # localization_languages.code is referenced by foreign keys (settings, state map), and
    # MySQL/MariaDB refuse to change a referenced column's charset (error 1833) even when
    # FOREIGN_KEY_CHECKS=0. To convert the tables safely:
    # 1. Query and drop all foreign key constraints referencing localization tables.
    # 2. Convert all localization tables to utf8mb4.
    # 3. Re-create the foreign keys with the matching utf8mb4 charset and collations.
    with connection.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        try:
            placeholders = ", ".join(["%s"] * len(TABLES))
            cursor.execute(
                f"""
                SELECT TABLE_NAME
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME IN ({placeholders})
                """,
                TABLES,
            )
            existing_tables = set(r[0] for r in cursor.fetchall())

            # Find all foreign keys referencing any of the localization tables
            cursor.execute(
                f"""
                SELECT
                    k.TABLE_NAME,
                    k.CONSTRAINT_NAME,
                    k.COLUMN_NAME,
                    k.REFERENCED_TABLE_NAME,
                    k.REFERENCED_COLUMN_NAME,
                    COALESCE(r.DELETE_RULE, 'RESTRICT') AS delete_rule,
                    COALESCE(r.UPDATE_RULE, 'RESTRICT') AS update_rule
                FROM information_schema.KEY_COLUMN_USAGE k
                LEFT JOIN information_schema.REFERENTIAL_CONSTRAINTS r
                  ON k.CONSTRAINT_NAME = r.CONSTRAINT_NAME
                 AND k.CONSTRAINT_SCHEMA = r.CONSTRAINT_SCHEMA
                WHERE k.TABLE_SCHEMA = DATABASE()
                  AND k.REFERENCED_TABLE_NAME IN ({placeholders})
                """,
                TABLES,
            )
            fks = cursor.fetchall()

            # Step 1: Drop foreign keys
            for row in fks:
                tbl_name, c_name = row[0], row[1]
                try:
                    cursor.execute(f"ALTER TABLE `{tbl_name}` DROP FOREIGN KEY `{c_name}`")
                except Exception:
                    pass

            # Step 2: Convert existing tables to utf8mb4
            for table in TABLES:
                if table in existing_tables:
                    cursor.execute(
                        f"ALTER TABLE `{table}` CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )

            # Step 3: Re-add foreign keys
            for row in fks:
                tbl_name, c_name, col_name, ref_tbl, ref_col, del_rule, up_rule = row
                sql = (
                    f"ALTER TABLE `{tbl_name}` "
                    f"ADD CONSTRAINT `{c_name}` "
                    f"FOREIGN KEY (`{col_name}`) REFERENCES `{ref_tbl}` (`{ref_col}`)"
                )
                if del_rule and del_rule.upper() not in ("RESTRICT", "NO ACTION"):
                    sql += f" ON DELETE {del_rule}"
                if up_rule and up_rule.upper() not in ("RESTRICT", "NO ACTION"):
                    sql += f" ON UPDATE {up_rule}"
                try:
                    cursor.execute(sql)
                except Exception:
                    pass

            # Step 4: Fallback ensure known FKs exist if not already present
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'localization_settings'
                  AND COLUMN_NAME = 'default_language_id'
                  AND REFERENCED_TABLE_NAME = 'localization_languages'
                """
            )
            if (
                cursor.fetchone()[0] == 0
                and "localization_settings" in existing_tables
                and "localization_languages" in existing_tables
            ):
                try:
                    cursor.execute(
                        """
                        ALTER TABLE `localization_settings`
                        ADD CONSTRAINT `fk_loc_settings_default_lang`
                        FOREIGN KEY (`default_language_id`) REFERENCES `localization_languages` (`code`)
                        ON DELETE RESTRICT
                        """
                    )
                except Exception:
                    pass

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'localization_state_languages'
                  AND COLUMN_NAME = 'language_id'
                  AND REFERENCED_TABLE_NAME = 'localization_languages'
                """
            )
            if (
                cursor.fetchone()[0] == 0
                and "localization_state_languages" in existing_tables
                and "localization_languages" in existing_tables
            ):
                try:
                    cursor.execute(
                        """
                        ALTER TABLE `localization_state_languages`
                        ADD CONSTRAINT `fk_loc_state_lang_language`
                        FOREIGN KEY (`language_id`) REFERENCES `localization_languages` (`code`)
                        ON DELETE SET NULL
                        """
                    )
                except Exception:
                    pass
        finally:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")


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
