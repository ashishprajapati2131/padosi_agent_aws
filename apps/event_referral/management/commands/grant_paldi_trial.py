from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.agents.services.account_auth import agent_has_completed_payment
from apps.event_referral.models import EventReferralParticipant
from apps.event_referral.services.participant_service import admin_grant_win


class Command(BaseCommand):
    help = (
        "Give every unpaid Paldi participant a temporary plan (same as admin "
        '"Grant plan -> Temporary"). Agents who paid, and participants who already '
        "won, are skipped. Dry run unless --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--until",
            default="2026-11-23",
            help="Last day of the trial (YYYY-MM-DD), inclusive.",
        )
        parser.add_argument(
            "--plan", default="basic", choices=["basic", "professional"]
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write changes. Without it, only prints counts.",
        )

    def handle(self, *args, **opts):
        try:
            until = datetime.strptime(opts["until"], "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
        except ValueError:
            raise CommandError("--until must be YYYY-MM-DD")
        if until <= datetime.now():
            raise CommandError("--until is in the past")

        granted = paid = won = 0
        qs = EventReferralParticipant.objects.select_related("agent").order_by("id")
        for p in qs.iterator():
            if agent_has_completed_payment(p.agent):
                paid += 1
                continue
            # A won participant already has a plan (earned or a permanent grant); a
            # temporary grant would replace it and take it away on expiry.
            if p.status == EventReferralParticipant.STATUS_WON:
                won += 1
                continue
            granted += 1
            if opts["apply"]:
                admin_grant_win(p, plan_slug=opts["plan"], expires_at=until)

        mode = "Granted" if opts["apply"] else "DRY RUN - would grant"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode} {opts['plan']} until {until:%Y-%m-%d %H:%M} to {granted} participants. "
                f"Skipped: {paid} paid, {won} already won. Total: {granted + paid + won}."
            )
        )
