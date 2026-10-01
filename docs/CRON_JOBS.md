# Scheduled jobs

**No cPanel cron is needed.** Cron did not run reliably on this host (it was
reverted in `236fd60`), so the website starts its own jobs:
`apps.agents.middleware.BackgroundJobsMiddleware` checks after each response
whether a job is due and, if so, runs it once in a background thread
(`apps/agents/services/background_jobs.py`). The claim is stored in the
shared cache, so only one app process runs it per interval. If the thread
dies (Passenger recycle, deploy), the next request after the interval runs it
again; every job is safe to re-run.

| Every | Job | What it does |
|---|---|---|
| 1 hour | invoice retry | Razorpay-paid subscriptions from the last 2 days with no invoice (older than 15 min) get the normal invoice PDF, welcome email and sheet sync. At most 3 automatic attempts per subscription, so a broken invoice never resends the welcome email every hour. |
| 30 min | Paldi expirations | Marks challengers WON or BLOCKED once their deadline passes (also happens when they open their dashboard). |

Jobs need traffic: with no visitors for a while they run on the next visit.
Turn off with `BACKGROUND_JOBS_ENABLED=False` in `.env`; they are off when
`DEBUG=True` and always off in tests. Log lines start with `[bgjobs]`.

## Not scheduled (run by hand over SSH when needed)

```
cd <app root> && /home/<cpanel-user>/virtualenv/padosiagentdjango/src/3.11/bin/python manage.py <command>
```

- `expire_subscriptions [--apply]`: only matters once the expiry switch (Admin → Settings → Security) is ON; access itself is checked live at login.
- `recover_orphaned_payments --days 60 [--apply]`: lists captured registration payments that never activated an agent, and possible double charges (never auto-activated; refund those in Razorpay).
- `retry_missing_invoices --days 60 [--apply]`: same as the hourly job, for a longer window and without the 3-attempt limit.
- `backup_database --tag manual`: the deploy script already backs up before every migration.

## One-time after the 2026-10-01 audit deploy

1. Migration `agents.0033_index_razorpay_lookup_columns` runs automatically on
   deploy (the deploy script backs up the DB first).
2. Run `recover_orphaned_payments --days 60` (dry run). For each listed agent
   check Razorpay, then run it again with `--apply`.
3. Run `retry_missing_invoices --days 60` (dry run), then with `--apply`.

`restore_database`, `repair_imported_agent_data`, `unify_plan_display_names`,
`import_blacklisted_agents`, `seed_*`, `test_email`, `verify_production_env`
are manual-only.
