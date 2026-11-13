import logging
from datetime import datetime
from html import escape

from django.core.management.base import BaseCommand, CommandError

from apps.agents.services.account_auth import agent_has_completed_payment
from apps.event_referral.models import EventReferralParticipant
from apps.event_referral.services.participant_service import admin_grant_win

logger = logging.getLogger(__name__)


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
        parser.add_argument(
            "--email-granted",
            action="store_true",
            help="Email-only: email agents who already hold this exact trial (same plan and end) "
            "and grant nobody new. Skips agents already emailed unless --force.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Also re-send to agents whose trial email was already sent.",
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

        granted = paid = won = emailed = already = same = not_granted = 0
        failed = []
        qs = EventReferralParticipant.objects.select_related("agent").order_by("id")
        for p in qs.iterator():
            if agent_has_completed_payment(p.agent):
                paid += 1
                continue
            # A won participant already has a plan (earned or a permanent grant); a
            # temporary grant would replace it and take it away on expiry.
            if p.status == EventReferralParticipant.STATUS_WON:
                won += 1
                same_trial = (
                    p.grant_plan_slug == opts["plan"] and p.grant_expires_at == until
                )
                if opts["apply"] and p.grant_expires_at and not agent_has_completed_payment(p.agent):
                    if p.agent.status == "pending_approval":
                        p.agent.status = "event_challenge"
                        p.agent.save(update_fields=["status", "updated_at"])
                same += same_trial
                # Granted earlier but the email never went out (failed or the run crashed).
                if same_trial and (opts["force"] or not p.win_emailed_at):
                    already += 1
                    if opts["apply"]:
                        if self._email_and_mark(p, opts["plan"], until):
                            emailed += 1
                        else:
                            failed.append(p.agent.email or f"agent #{p.agent_id}")
                continue
            if opts["email_granted"]:
                not_granted += 1  # email-only run: new participants get nothing
                continue
            granted += 1
            if opts["apply"]:
                admin_grant_win(p, plan_slug=opts["plan"], expires_at=until)
                # win_emailed_at lets a re-run send this if it fails or the run crashes here.
                if self._email_and_mark(p, opts["plan"], until):
                    emailed += 1
                else:
                    failed.append(p.agent.email or f"agent #{p.agent_id}")

        if opts["email_granted"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{'Emailing' if opts['apply'] else 'DRY RUN - would email'} {already} agents who "
                    f"already have this trial ({same - already} already emailed; --force re-sends). "
                    f"No new grants ({not_granted} without the trial left as they are). "
                    f"Skipped: {paid} paid, {won - same} won with another plan. "
                    f"Total: {won + paid + not_granted}."
                )
            )
        else:
            mode = "Granted" if opts["apply"] else "DRY RUN - would grant (and email)"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{mode} {opts['plan']} until {until:%Y-%m-%d %H:%M} to {granted} participants. "
                    f"Skipped: {paid} paid, {won} already won. Total: {granted + paid + won}. "
                    f"{'Emailing' if opts['apply'] else 'Would email'} {already} granted earlier "
                    f"whose email was not sent."
                )
            )
        if opts["apply"]:
            self.stdout.write(f"Emails sent: {emailed}, failed: {len(failed)}.")
            for who in failed:
                self.stderr.write(f"  email failed: {who}")

    def _email_and_mark(self, p, plan, until):
        if not self._email(p.agent, plan, until):
            return False
        EventReferralParticipant.objects.filter(pk=p.pk).update(
            win_emailed_at=datetime.now()
        )
        return True

    def _email(self, agent, plan, until):
        """Festive trial email. Returns False (never raises) so one bad address cannot stop the grants."""
        from django.conf import settings
        from apps.agents.services.brevo import email_service

        to = (agent.email or "").strip()
        if not to:
            return False
        name = escape((agent.fullname or "").strip() or "there")
        login = (getattr(settings, "APP_URL", "") or "https://padosiagent.com").rstrip(
            "/"
        ) + "/agent-login/"
        html = (
            '<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;color:#1f2937;line-height:1.6">'
            '<p style="font-size:32px;text-align:center;margin:0">🪔✨🪔</p>'
            f'<h2 style="text-align:center;color:#0f766e;margin:8px 0">Diwali to Dev Diwali: your {plan.title()} plan is on us!</h2>'
            f"<p>Namaste {name},</p>"
            f"<p>This festive season PadosiAgent has unlocked every <b>{plan.title()} plan</b> feature for you, "
            f"<b>free till {until:%d %B %Y}</b>.</p>"
            "<p>Complete your profile, collect reviews from your customers and welcome new families "
            "as their trusted Padosi.</p>"
            f'<p style="text-align:center;margin:24px 0"><a href="{login}" style="background:#0f766e;color:#fff;'
            'padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold">Open my dashboard</a></p>'
            "<p>Happy Diwali, Saal Mubarak &amp; Happy Dev Diwali!<br>Team PadosiAgent</p></div>"
        )
        try:
            return bool(
                email_service.send_generic(
                    to,
                    agent.fullname or "",
                    f"🪔 Your free {plan.title()} plan till {until:%d %b}",
                    html,
                )
            )
        except Exception:
            logger.exception("Paldi trial email failed for agent #%s", agent.pk)
            return False
