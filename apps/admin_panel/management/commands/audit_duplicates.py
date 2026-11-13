from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.agents.models import AgentReview, Invoice
from apps.referral_championship.models import ChampionshipReferral

SAMPLE = 20


class Command(BaseCommand):
    help = "Read-only: report duplicate reviews, championship referrals and invoices."

    def handle(self, *args, **opts):
        checks = [
            (
                "AgentReview (agent_id, reviewer_mobile)",
                AgentReview.objects.exclude(reviewer_mobile__isnull=True).exclude(
                    reviewer_mobile=""
                ),
                ("agent_id", "reviewer_mobile"),
            ),
            (
                "ChampionshipReferral (campaign_id, referred_agent_id)",
                # NULL referred_agent rows (link opened, no signup yet) never clash in a unique index.
                ChampionshipReferral.objects.exclude(referred_agent__isnull=True),
                ("campaign_id", "referred_agent_id"),
            ),
            (
                "Invoice razorpay_payment_id",
                Invoice.objects.exclude(razorpay_payment_id__isnull=True).exclude(
                    razorpay_payment_id=""
                ),
                ("razorpay_payment_id",),
            ),
        ]
        for label, qs, keys in checks:
            dups = (
                qs.values(*keys)
                .annotate(n=Count("id"))
                .filter(n__gt=1)
                .order_by(*keys)
            )
            total = dups.count()
            self.stdout.write(f"{label}: {total} duplicate keys")
            for row in dups[:SAMPLE]:
                key = ", ".join(f"{k}={row[k]}" for k in keys)
                self.stdout.write(f"  {key} (rows: {row['n']})")
