"""Mark ended paid subscriptions as expired and list the ones due soon.

Access itself is decided live (agent_has_completed_payment checks
expires_at while the "Enforce subscription expiry" switch is ON); this
command keeps subscription statuses truthful for admin pages and prints who
is due, so they can be reminded. It does nothing while the switch is OFF.

Suggested cPanel cron (daily):
    python manage.py expire_subscriptions --apply
"""
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Mark expired subscriptions (only while expiry is enforced) and list those expiring soon.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Write status=expired (default: dry run).')
        parser.add_argument('--due-days', type=int, default=7, help='Also list subscriptions ending within N days.')

    def handle(self, *args, **options):
        from apps.agents.models import AgentSubscription
        from apps.agents.services.subscription_expiry import expiry_enforced

        if not expiry_enforced():
            self.stdout.write('Subscription expiry is OFF (Admin > Settings > Security); nothing to do.')
            return

        now = datetime.now()
        ended = (AgentSubscription.objects
                 .filter(payment_status='completed', status='active', expires_at__lt=now)
                 .select_related('agent'))
        count = 0
        for sub in ended:
            count += 1
            self.stdout.write(f'EXPIRED  sub #{sub.pk}  agent #{sub.agent_id} {getattr(sub.agent, "email", "")}  '
                              f'{sub.selected_plan}  ended {sub.expires_at:%Y-%m-%d}')
        if options['apply'] and count:
            ended.update(status='expired')

        due = (AgentSubscription.objects
               .filter(payment_status='completed', status='active',
                       expires_at__gte=now, expires_at__lt=now + timedelta(days=options['due_days']))
               .select_related('agent').order_by('expires_at'))
        for sub in due:
            self.stdout.write(f'DUE      sub #{sub.pk}  agent #{sub.agent_id} {getattr(sub.agent, "email", "")}  '
                              f'{sub.selected_plan}  ends {sub.expires_at:%Y-%m-%d}')

        mode = 'marked expired' if options['apply'] else 'dry run, nothing changed'
        self.stdout.write(self.style.SUCCESS(f'{count} expired ({mode}), {due.count()} due within {options["due_days"]} days.'))
