"""
WhatsApp a message to every active agent, with their own public profile link.

Dry run (default) only prints the count and a sample:
    python manage.py wa_broadcast_active_agents --message-file diwali.txt
Real send:
    python manage.py wa_broadcast_active_agents --message-file diwali.txt --send

Re-running is safe: numbers that already got this exact text are skipped.
"""

import random
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.agents.models import Agent
from apps.agents.services.og_urls import CANONICAL_PADOSI_ORIGIN
from apps.wa_agent_bot.models import WaBotMessageLog
from apps.wa_agent_bot.services.message_sender import send_text_message

CATEGORY = "broadcast"


def build_text(message, agent, base):
    link = f"{base}/{agent.state_code}/{agent.agent_slug}/"
    return f"{message.strip()}\n\nYour profile: {link}"


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
            "--base-url",
            default=getattr(settings, "APP_URL", "") or CANONICAL_PADOSI_ORIGIN,
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
        base = opts["base_url"].rstrip("/")

        agents = list(
            Agent.objects.filter(status="active")
            .select_related("profile")
            .order_by("id")
        )
        seen, targets = set(), []
        for a in agents:
            digits = "".join(c for c in (a.mobile or "") if c.isdigit())[-10:]
            if (
                len(digits) != 10 or digits in seen
            ):  # skip blank/invalid numbers and duplicates
                continue
            seen.add(digits)
            targets.append((a, digits))
        if opts["limit"]:
            targets = targets[: opts["limit"]]

        self.stdout.write(
            f"Active agents: {len(agents)} | valid unique numbers: {len(targets)}"
        )
        if targets:
            a, d = targets[0]
            self.stdout.write(
                f"\n--- Sample for {a.fullname} ({d}) ---\n{build_text(message, a, base)}\n---"
            )
        if not opts["send"]:
            self.stdout.write(
                self.style.WARNING("Dry run: nothing sent. Add --send to send.")
            )
            return

        sent = failed = skipped = 0
        for i, (agent, digits) in enumerate(targets, 1):
            text = build_text(message, agent, base)
            already = WaBotMessageLog.objects.filter(
                phone_number__endswith=digits,
                category=CATEGORY,
                status=WaBotMessageLog.STATUS_SENT,
                content=text[:5000],
            ).exists()
            if already:
                skipped += 1
                continue
            result = send_text_message(digits, text, category=CATEGORY)
            if result.get("success"):
                sent += 1
            else:
                failed += 1
                self.stderr.write(
                    f"FAIL {agent.id} {agent.fullname} {digits}: {result.get('error')}"
                )
            self.stdout.write(
                f"[{i}/{len(targets)}] sent={sent} failed={failed} skipped={skipped}"
            )
            time.sleep(random.uniform(opts["min_delay"], opts["max_delay"]))

        self.stdout.write(
            self.style.SUCCESS(f"Done. sent={sent} failed={failed} skipped={skipped}")
        )
