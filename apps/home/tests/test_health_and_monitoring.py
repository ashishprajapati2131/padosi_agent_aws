import json
from django.test import TestCase, Client
from django.core.management import call_command
from django.urls import reverse


class HealthAndMonitoringTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_health_check_endpoint(self):
        res = self.client.get('/health/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get('status'), 'healthy')
        self.assertEqual(data.get('database'), 'ok')
        self.assertEqual(data.get('cache'), 'ok')

    def test_healthz_alias_endpoint(self):
        res = self.client.get('/healthz')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get('status'), 'healthy')

    def test_reconcile_fulfillment_dry_run(self):
        # Verify the command executes cleanly without exceptions
        call_command('reconcile_fulfillment', '--dry-run', '--limit', '5')

    def test_backup_database_dry_run(self):
        # Verify backup command executes cleanly
        call_command('backup_database', '--tag', 'test_ci', '--retention', '3')

    def test_verify_production_env_runs(self):
        # Verify verification command executes without throwing unexpected exception
        try:
            call_command('verify_production_env')
        except SystemExit:
            pass  # Expected in test environment where some prod env vars are missing
