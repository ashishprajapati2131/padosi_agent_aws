"""
WhatsApp a message to every active agent, with their own public profile link.
The admin page Admin → WhatsApp → Broadcast does the same with agent selection and sheet upload.

Dry run (default) only prints the count and a sample:
    python manage.py wa_broadcast_active_agents --message-file diwali.txt
Real send:
    python manage.py wa_broadcast_active_agents --message-file diwali.txt --send

Re-running is safe: numbers that already got this exact text are skipped.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.agents.models import Agent
from apps.wa_agent_bot.services import broadcast


class Command(BaseCommand):
    help = "WhatsApp a message + profile link to all active agents (dry run unless --send)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--message-file", required=True, help="UTF-8 text file with the message"
        )
        parser.add_argument(
            "--send", action="store_true", help="Actually send (default is dry run)"
        )
        parser.add_argument(
            "--base-url", default="", help="Profile link origin (default: APP_URL)"
        )
        parser.add_argument(
            "--min-delay",
            type=float,
            default=6,
            help="Seconds between sends (anti-ban)",
        )
        parser.add_argument("--max-delay", type=float, default=12)
        parser.add_argument(
            "--limit", type=int, default=0, help="Send to first N only (0 = all)"
        )

    def handle(self, *args, **opts):
        try:
            with open(opts["message_file"], encoding="utf-8") as f:
                message = f.read()
        except OSError as e:
            raise CommandError(e)
        if not message.strip():
            raise CommandError("Message file is empty")

        agents = (
            Agent.objects.filter(status="active")
            .select_related("profile")
            .order_by("id")
        )
        recipients = broadcast.build_recipients(
            agents=agents, base=opts["base_url"] or None
        )
        if opts["limit"]:
            recipients = recipients[: opts["limit"]]

        self.stdout.write(
            f"Active agents: {agents.count()} | valid unique numbers: {len(recipients)}"
        )
        if recipients:
            r = recipients[0]
            self.stdout.write(
                f"\n--- Sample for {r['name']} ({r['phone']}) ---\n"
                f"{broadcast.render_text(message, r['name'], r['link'])}\n---"
            )
        if not opts["send"]:
            self.stdout.write(
                self.style.WARNING("Dry run: nothing sent. Add --send to send.")
            )
            return

        def progress(s):
            self.stdout.write(
                f"[{s['sent'] + s['failed'] + s['skipped']}/{s['total']}] "
                f"sent={s['sent']} failed={s['failed']} skipped={s['skipped']}"
            )

        stats = broadcast.run_broadcast(
            recipients, message, opts["min_delay"], opts["max_delay"], progress
        )
        for err in stats["errors"]:
            self.stderr.write(f"FAIL {err}")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. sent={stats['sent']} failed={stats['failed']} skipped={stats['skipped']}"
            )
        )
