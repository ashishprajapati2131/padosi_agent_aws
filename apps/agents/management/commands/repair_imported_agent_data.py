"""
Repair PHP → Django import conflicts:

- Duplicate agent emails (login picked the incomplete row)
- Duplicate agent_profiles for one agent_id (profile page 500)
- agents.user_id pointing at Laravel users.id instead of auth_user
- investment_types stored as {} instead of []

Usage:
    python manage.py repair_imported_agent_data
    python manage.py repair_imported_agent_data --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.contrib.auth.models import User as AuthUser

from apps.agents.models import Agent, AgentProfile

CHILD_TABLES = [
    "agent_achievement_photos",
    "agent_approval_requests",
    "agent_bio_generation_logs",
    "agent_career_timelines",
    "agent_device_tokens",
    "agent_family_licenses",
    "agent_insurance_company",
    "agent_insurance_segments",
    "agent_invoices",
    "agent_leads",
    "agent_lead_preferences",
    "agent_notifications",
    "agent_performance_stats",
    "agent_portfolios",
    "agent_product_expertise",
    "agent_profiles",
    "agent_profile_edit_logs",
    "agent_profile_views",
    "agent_reviews",
    "agent_serviceable_cities",
    "agent_service_pincodes",
    "agent_subscriptions",
    "agent_user_type",
    "favorite_agents",
    "free_trial_history",
    "invoices",
    "profile_leads",
    "referral_codes",
    "user_plan_progress",
    "user_sessions",
]

STATUS_RANK = {
    "active": 0,
    "pending_approval": 1,
    "pending_payment": 2,
    "pending_accounts_payment": 3,
    "inactive": 4,
    "suspended": 5,
    "blacklisted": 6,
    "rejected": 7,
    "incomplete": 8,
}


class Command(BaseCommand):
    help = "Fix PHP-imported agent duplicates and broken Django user FKs"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        self.stdout.write(f"Mode: {'dry-run' if dry else 'apply'}")

        with transaction.atomic():
            cleared = self._clear_invalid_user_ids(dry)
            merged = self._merge_duplicate_emails(dry)
            profiles = self._collapse_duplicate_profiles(dry)
            json_fixed = self._fix_investment_types(dry)
            slugs = self._fill_empty_slugs(dry)
            if dry:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"invalid user_id cleared={cleared}, duplicate emails merged={merged}, "
            f"extra profiles removed={profiles}, investment_types fixed={json_fixed}, slugs filled={slugs}"
        ))

    def _clear_invalid_user_ids(self, dry):
        auth_ids = set(AuthUser.objects.values_list("id", flat=True))
        broken = list(
            Agent.objects.exclude(user_id__isnull=True).exclude(user_id__in=auth_ids).values_list("id", "email", "user_id")
        )
        self.stdout.write(f"Broken user_id rows: {len(broken)}")
        if not dry and broken:
            Agent.objects.filter(id__in=[row[0] for row in broken]).update(user_id=None)
        return len(broken)

    def _merge_duplicate_emails(self, dry):
        from collections import defaultdict
        by_email = defaultdict(list)
        for agent in Agent.objects.all().only("id", "email", "status"):
            if agent.email:
                by_email[agent.email.strip().lower()].append(agent)

        merged = 0
        for email, agents in by_email.items():
            if len(agents) < 2:
                continue
            winner = self._pick_winner(agents)
            losers = [a for a in agents if a.id != winner.id]
            self.stdout.write(
                f"  email {email}: keep #{winner.id} ({winner.status}), "
                f"remove {[a.id for a in losers]}"
            )
            if dry:
                merged += len(losers)
                continue
            for loser in losers:
                self._reassign_then_delete(winner, loser)
                merged += 1
        return merged

    def _pick_winner(self, agents):
        profile_ids = set(
            AgentProfile.objects.filter(agent_id__in=[a.id for a in agents]).values_list("agent_id", flat=True)
        )

        def key(agent):
            return (
                STATUS_RANK.get(agent.status or "", 99),
                0 if agent.id in profile_ids else 1,
                -agent.id,
            )

        return sorted(agents, key=key)[0]

    def _reassign_then_delete(self, winner, loser):
        with connection.cursor() as cursor:
            winner_has_profile = AgentProfile.objects.filter(agent_id=winner.id).exists()
            if not winner_has_profile:
                cursor.execute(
                    "UPDATE agent_profiles SET agent_id = %s WHERE agent_id = %s",
                    [winner.id, loser.id],
                )
            cursor.execute("SET FOREIGN_KEY_CHECKS=0")
            for table in CHILD_TABLES:
                cursor.execute(
                    f"DELETE FROM `{table}` WHERE agent_id = %s",
                    [loser.id],
                )
            cursor.execute(
                "DELETE FROM referral_usages WHERE referrer_agent_id = %s OR referred_agent_id = %s",
                [loser.id, loser.id],
            )
            cursor.execute("DELETE FROM agents WHERE id = %s", [loser.id])
            cursor.execute("SET FOREIGN_KEY_CHECKS=1")

    def _collapse_duplicate_profiles(self, dry):
        removed = 0
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT agent_id, GROUP_CONCAT(id ORDER BY id DESC) ids
                FROM agent_profiles
                GROUP BY agent_id
                HAVING COUNT(*) > 1
                """
            )
            for agent_id, ids in cursor.fetchall():
                id_list = [int(x) for x in str(ids).split(",") if x]
                keep, extras = id_list[0], id_list[1:]
                self.stdout.write(f"  profiles for agent #{agent_id}: keep {keep}, remove {extras}")
                if not dry and extras:
                    cursor.execute(
                        "DELETE FROM agent_profiles WHERE id IN (" + ",".join(["%s"] * len(extras)) + ")",
                        extras,
                    )
                    removed += len(extras)
                else:
                    removed += len(extras)
        return removed

    def _fix_investment_types(self, dry):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) FROM agent_profiles
                WHERE investment_types = '{}' OR investment_types = 'null'
                """
            )
            count = cursor.fetchone()[0]
            if not dry and count:
                cursor.execute(
                    """
                    UPDATE agent_profiles
                    SET investment_types = '[]'
                    WHERE investment_types = '{}' OR investment_types = 'null'
                    """
                )
        self.stdout.write(f"investment_types empty-object to list: {count}")
        return count

    def _fill_empty_slugs(self, dry):
        from django.utils.text import slugify
        from django.db.models import Q
        empty = list(AgentProfile.objects.filter(Q(slug__isnull=True) | Q(slug="")))
        filled = 0
        for profile in empty:
            name = profile.display_name or (profile.agent.fullname if profile.agent_id else "agent")
            base = slugify(name) or f"agent-{profile.agent_id}"
            slug = base
            n = 1
            while AgentProfile.objects.filter(slug=slug).exclude(pk=profile.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.stdout.write(f"  slug for profile #{profile.id}: {slug}")
            if not dry:
                profile.slug = slug
                profile.save(update_fields=["slug"])
            filled += 1
        return filled
