"""Scheduled jobs without cron (F-21/F-39 follow-up): cPanel cron does not
run on this host, so due jobs start from web traffic in a daemon thread,
once per interval across processes, and never during tests."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.agents.models import Agent, AgentSubscription
from apps.agents.services import background_jobs
from apps.agents.services.background_jobs import maybe_run_due_jobs, retry_missing_invoices

FULFIL = 'apps.agents.services.post_payment.fulfill_invoice_and_welcome'


class _FakeThread:
    started = []

    def __init__(self, target=None, args=(), **kwargs):
        self.target, self.args = target, args

    def start(self):
        _FakeThread.started.append(self.args[0])


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class BackgroundJobsTests(TestCase):
    def setUp(self):
        cache.clear()
        _FakeThread.started = []
        agent = Agent.objects.create(fullname='Bg', email='bg.jobs@example.com', mobile='9000000411')
        self.sub = AgentSubscription.objects.create(
            agent=agent, selected_plan="Starter's Plan", registration_amount='2359.00',
            payment_status='completed', status='active', starts_at=datetime.now() - timedelta(hours=1),
            razorpay_order_id='order_BGJOB0000001', razorpay_payment_id='pay_BGJOB00000001')

    def test_never_runs_during_tests(self):
        with patch.object(background_jobs.threading, 'Thread', _FakeThread):
            self.assertEqual(maybe_run_due_jobs(), [])

    @override_settings(TESTING=False, BACKGROUND_JOBS_ENABLED=True)
    def test_each_job_starts_once_per_interval(self):
        with patch.object(background_jobs.threading, 'Thread', _FakeThread):
            self.assertEqual(maybe_run_due_jobs(), ['invoice-retry', 'paldi-expirations'])
            self.assertEqual(maybe_run_due_jobs(), [])
            self.client.get('/')                       # middleware path: nothing due yet
        self.assertEqual(_FakeThread.started, ['invoice-retry', 'paldi-expirations'])

    @override_settings(TESTING=False, BACKGROUND_JOBS_ENABLED=False)
    def test_switch_off_in_settings(self):
        with patch.object(background_jobs.threading, 'Thread', _FakeThread):
            self.assertEqual(maybe_run_due_jobs(), [])

    @override_settings(TESTING=False, BACKGROUND_JOBS_ENABLED=True)
    def test_a_request_triggers_due_jobs(self):
        with patch.object(background_jobs.threading, 'Thread', _FakeThread):
            self.client.get('/')
        self.assertEqual(_FakeThread.started, ['invoice-retry', 'paldi-expirations'])

    def test_invoice_job_fulfils_the_missing_invoice(self):
        with patch(FULFIL, return_value=MagicMock(invoice_number='PA/BG/1')) as fulfil:
            background_jobs._run('invoice-retry', background_jobs._invoice_job)
        fulfil.assert_called_once()
        self.assertEqual(fulfil.call_args.args[1].pk, self.sub.pk)

    def test_automatic_retries_stop_after_three_attempts(self):
        with patch(FULFIL, side_effect=RuntimeError('pdf broken')) as fulfil:
            for _ in range(5):
                retry_missing_invoices(days=2, apply=True, max_attempts=3)
        self.assertEqual(fulfil.call_count, 3)       # welcome email not resent every hour

    def test_running_retry_is_not_doubled(self):
        cache.add(f'bgjobs:invoice-lock:{self.sub.pk}', 1, timeout=60)
        lines = []
        with patch(FULFIL) as fulfil:
            retry_missing_invoices(days=2, apply=True, write=lines.append)
        fulfil.assert_not_called()
        self.assertTrue(any('another retry is running' in line for line in lines))

    def test_paldi_job_runs_the_expiry_command(self):
        with patch('django.core.management.call_command') as call:
            background_jobs._paldi_expiry_job()
        self.assertEqual(call.call_args.args[0], 'process_event_referral_expirations')
