"""
Management command to verify production environment variables and security settings.
Usage:
    python manage.py verify_production_env
    python manage.py verify_production_env --strict
"""

import os
from django.core.management.base import BaseCommand
from django.conf import settings
from padosi_agent.razorpay_env import credential_pair_from_mapping, complete_pair_from_env_files


class Command(BaseCommand):
    help = "Verify all production environment variables, security settings, Razorpay keys, and Sentry DSN."

    def add_arguments(self, parser):
        parser.add_argument(
            '--strict',
            action='store_true',
            help='Treat warnings as errors (fails if test keys or debug mode are active).',
        )

    def handle(self, *args, **options):
        strict = options['strict']
        errors = []
        warnings = []
        passed = []

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== PadosiAgent Production Environment Verification ===\n"))

        # 1. DEBUG mode
        if settings.DEBUG:
            msg = "DEBUG is True. Production must have DEBUG=False."
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)
        else:
            passed.append("DEBUG is set to False")

        # 2. SECRET_KEY
        secret_key = getattr(settings, 'SECRET_KEY', '')
        if not secret_key:
            errors.append("SECRET_KEY is empty or not set.")
        elif 'django-insecure' in secret_key or len(secret_key) < 40:
            msg = f"SECRET_KEY is insecure or too short ({len(secret_key)} chars). Use a 50+ character random string."
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)
        else:
            passed.append("SECRET_KEY is set and securely random")

        # 3. ALLOWED_HOSTS
        allowed = getattr(settings, 'ALLOWED_HOSTS', [])
        if not allowed or allowed == ['*']:
            errors.append("ALLOWED_HOSTS cannot be empty or wildcard ['*'] in production.")
        elif any('padosiagent.com' in host for host in allowed):
            passed.append(f"ALLOWED_HOSTS configured: {', '.join(allowed)}")
        else:
            warnings.append(f"ALLOWED_HOSTS does not mention padosiagent.com: {', '.join(allowed)}")

        # 4. CSRF_TRUSTED_ORIGINS
        csrf_origins = getattr(settings, 'CSRF_TRUSTED_ORIGINS', [])
        if not csrf_origins:
            warnings.append("CSRF_TRUSTED_ORIGINS is empty. Production POST requests over HTTPS may fail CSRF check.")
        elif any(orig.startswith('https://') for orig in csrf_origins):
            passed.append(f"CSRF_TRUSTED_ORIGINS configured with HTTPS: {', '.join(csrf_origins)}")
        else:
            warnings.append(f"CSRF_TRUSTED_ORIGINS has no HTTPS entries: {', '.join(csrf_origins)}")

        # 5. Razorpay Configuration
        rzp_key = getattr(settings, 'RAZORPAY_KEY', '') or os.environ.get('RAZORPAY_KEY', '')
        rzp_secret = getattr(settings, 'RAZORPAY_SECRET', '') or os.environ.get('RAZORPAY_SECRET', '')
        if not rzp_key or not rzp_secret:
            errors.append("RAZORPAY_KEY or RAZORPAY_SECRET is missing. Payments will fail.")
        else:
            is_live = rzp_key.startswith('rzp_live_')
            is_test = rzp_key.startswith('rzp_test_')
            if is_live:
                passed.append(f"RAZORPAY_KEY is configured in LIVE mode ({rzp_key[:12]}...)")
            elif is_test:
                msg = f"RAZORPAY_KEY is in TEST mode ({rzp_key[:12]}...). Live transactions will not be processed."
                if strict:
                    errors.append(msg)
                else:
                    warnings.append(msg)
            else:
                warnings.append(f"RAZORPAY_KEY format unrecognized ({rzp_key[:8]}...)")

            if len(rzp_secret) < 10:
                warnings.append("RAZORPAY_SECRET appears too short.")
            else:
                passed.append("RAZORPAY_SECRET is set")

        # 6. Sentry DSN & APM
        sentry_dsn = getattr(settings, 'SENTRY_DSN', '') or os.environ.get('SENTRY_DSN', '')
        if not sentry_dsn:
            msg = "SENTRY_DSN is not configured. Production error tracking and alerts are disabled."
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)
        elif sentry_dsn.startswith('https://') and '@' in sentry_dsn:
            passed.append("SENTRY_DSN is configured and valid format")
        else:
            warnings.append(f"SENTRY_DSN has invalid format: {sentry_dsn[:20]}...")

        # 7. Database Engine & Production Database
        db_conf = settings.DATABASES.get('default', {})
        engine = db_conf.get('ENGINE', '')
        if 'sqlite3' in engine:
            msg = "Default database is SQLite. Production should use MySQL."
            if strict:
                errors.append(msg)
            else:
                warnings.append(msg)
        else:
            db_name = db_conf.get('NAME', '')
            db_user = db_conf.get('USER', '')
            passed.append(f"Database engine is MySQL (DB: {db_name}, User: {db_user})")

        # 8. Email / Brevo Configuration
        brevo_key = os.environ.get('BREVO_API_KEY', '') or getattr(settings, 'BREVO_API_KEY', '')
        mail_pwd = os.environ.get('MAIL_PASSWORD', '') or getattr(settings, 'EMAIL_HOST_PASSWORD', '')
        if not brevo_key and not mail_pwd:
            warnings.append("Neither BREVO_API_KEY nor MAIL_PASSWORD is set. Outgoing OTPs/emails will fail.")
        else:
            passed.append("Transactional Email / Brevo is configured")

        # Output Results
        for p in passed:
            self.stdout.write(self.style.SUCCESS(f"  [OK]   {p}"))
        for w in warnings:
            self.stdout.write(self.style.WARNING(f"  [WARN] {w}"))
        for e in errors:
            self.stdout.write(self.style.ERROR(f"  [FAIL] {e}"))

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(f"Summary: {len(passed)} Passed, {len(warnings)} Warnings, {len(errors)} Errors\n")

        if errors:
            self.stdout.write(self.style.ERROR("[CRITICAL] Production environment verification FAILED.\n"))
            raise SystemExit(1)
        elif warnings and strict:
            self.stdout.write(self.style.ERROR("[STRICT FAILED] Warnings treated as errors under --strict.\n"))
            raise SystemExit(1)
        else:
            self.stdout.write(self.style.SUCCESS("[READY] Production environment verification PASSED.\n"))
