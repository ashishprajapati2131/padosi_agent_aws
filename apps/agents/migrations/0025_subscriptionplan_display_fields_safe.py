from django.db import migrations
from django.utils.text import slugify


def _existing_columns(schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('SHOW COLUMNS FROM subscription_plans')
        return {row[0] for row in cursor.fetchall()}


def add_subscription_plan_display_fields(apps, schema_editor):
    existing = _existing_columns(schema_editor)
    SubscriptionPlan = apps.get_model('agents', 'SubscriptionPlan')
    table = SubscriptionPlan._meta.db_table

    alters = []
    if 'badge_text' not in existing:
        alters.append('ADD COLUMN `badge_text` varchar(50) NULL')
    if 'color_theme' not in existing:
        alters.append("ADD COLUMN `color_theme` varchar(50) NOT NULL DEFAULT 'starter-theme'")
    if 'description' not in existing:
        alters.append("ADD COLUMN `description` longtext NOT NULL DEFAULT ('')")
    if 'slug' not in existing:
        alters.append('ADD COLUMN `slug` varchar(50) NULL')
    if 'sort_order' not in existing:
        alters.append('ADD COLUMN `sort_order` int NOT NULL DEFAULT 0')

    if alters:
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(f'ALTER TABLE `{table}` {", ".join(alters)}')

    existing = _existing_columns(schema_editor)
    if 'slug' not in existing:
        return

    used = set(
        SubscriptionPlan.objects.exclude(slug__isnull=True)
        .exclude(slug='')
        .values_list('slug', flat=True)
    )
    for plan in SubscriptionPlan.objects.all().iterator():
        if plan.slug:
            continue
        base = slugify(plan.name or '') or f'plan-{plan.pk}'
        candidate = base
        n = 2
        while candidate in used:
            candidate = f'{base}-{n}'
            n += 1
        plan.slug = candidate
        plan.save(update_fields=['slug'])
        used.add(candidate)

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"SHOW INDEX FROM `{table}` WHERE Key_name = 'slug'")
        if not cursor.fetchall():
            cursor.execute(f'ALTER TABLE `{table}` ADD UNIQUE INDEX `slug` (`slug`)')


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0024_agentdraft_claimed_profile_fields'),
    ]

    operations = [
        migrations.RunPython(add_subscription_plan_display_fields, migrations.RunPython.noop),
    ]
