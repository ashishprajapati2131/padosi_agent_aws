"""Add the indexes the admin panel's hot queries need, only where the live DB lacks them.

Not a migration on purpose: several of these tables were created by Laravel and may already
have equivalent indexes under other names. A column-prefix check against information_schema
decides, so nothing is duplicated.

    python manage.py ensure_admin_indexes          # report only
    python manage.py ensure_admin_indexes --apply  # create the missing ones (MySQL / MariaDB)
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

# (table, columns, index name). Leading columns first: they must match the filter/order.
WANTED = [
    ("agents", ("status", "created_at"), "idx_agents_status_created"),
    ("agents", ("agent_pincode",), "idx_agents_pincode"),
    ("agents", ("plan_type", "trial_ends_at"), "idx_agents_plan_trial"),
    ("agent_subscriptions", ("agent_id", "payment_status"), "idx_subs_agent_payment"),
    (
        "agent_subscriptions",
        ("payment_status", "expires_at"),
        "idx_subs_payment_expires",
    ),
    ("agent_leads", ("lead_status",), "idx_leads_status"),
    ("agent_leads", ("created_at",), "idx_leads_created"),
    ("agent_reviews", ("agent_id", "is_approved"), "idx_reviews_agent_approved"),
    ("contact_submissions", ("status", "created_at"), "idx_contacts_status_created"),
]


def _existing_indexes(cursor, table):
    cursor.execute(
        "SELECT index_name, seq_in_index, column_name FROM information_schema.statistics "
        "WHERE table_schema = DATABASE() AND table_name = %s ORDER BY index_name, seq_in_index",
        [table],
    )
    found = {}
    for name, _, column in cursor.fetchall():
        found.setdefault(name, []).append(column.lower())
    return list(found.values())


def _covered(existing, columns):
    # An index whose leading columns equal ours already serves the same lookups.
    return any(idx[: len(columns)] == [c.lower() for c in columns] for idx in existing)


class Command(BaseCommand):
    help = (
        "Report (and with --apply create) missing indexes used by admin panel queries."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true", help="Create the missing indexes."
        )

    def handle(self, *args, **options):
        if connection.vendor != "mysql":
            raise CommandError("Only for the MySQL/MariaDB production database.")
        missing = []
        with connection.cursor() as cursor:
            for table, columns, name in WANTED:
                existing = _existing_indexes(cursor, table)
                if not existing and not self._table_exists(cursor, table):
                    self.stdout.write(f"skip {table}: table not found")
                    continue
                if _covered(existing, columns):
                    self.stdout.write(f"ok   {table}({', '.join(columns)})")
                else:
                    missing.append((table, columns, name))
                    self.stdout.write(
                        self.style.WARNING(f"MISSING {table}({', '.join(columns)})")
                    )
            if not options["apply"]:
                self.stdout.write(
                    f"{len(missing)} missing. Re-run with --apply to create them."
                )
                return
            for table, columns, name in missing:
                cols = ", ".join(f"`{c}`" for c in columns)
                self.stdout.write(f"creating {name} on {table} ...")
                cursor.execute(f"CREATE INDEX `{name}` ON `{table}` ({cols})")
        self.stdout.write(self.style.SUCCESS(f"Created {len(missing)} index(es)."))

    @staticmethod
    def _table_exists(cursor, table):
        cursor.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
            [table],
        )
        return cursor.fetchone() is not None
