# /check — Run Django system checks

Run Django's built-in health check + verify no pending migrations:

```bash
python manage.py check
```

```bash
python manage.py makemigrations --check --dry-run
```

Report any errors found. If clean, say "All checks passed ✓".
