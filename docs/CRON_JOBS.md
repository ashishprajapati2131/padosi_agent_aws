# Scheduled jobs (cPanel → Cron Jobs)

Payment and fulfilment code assumes these run. Without them, a paid agent whose
background invoice job died never gets an invoice, and Paldi challengers past
their deadline stay "active" until they next open a page.

All commands are run from the project folder with the cPanel virtualenv Python
that `scripts/deploy_godaddy.sh` uses:

```
cd <PROJECT_PATH> && /home/<cpanel-user>/virtualenv/padosiagentdjango/src/3.11/bin/python manage.py <command> >> logs/cron_<command>.log 2>&1
```

`<PROJECT_PATH>` is the `GODADDY_PROJECT_PATH` deploy secret. Make sure `logs/` exists.

| Schedule | Command | What it does | Safe to re-run |
|---|---|---|---|
| Hourly (`15 * * * *`) | `retry_missing_invoices --days 2 --apply` | Paid Razorpay subscriptions with no invoice (older than 15 min) get the normal invoice PDF, welcome email and sheet sync. | Yes: skips anything that already has an invoice. |
| Every 30 min (`*/30 * * * *`) | `process_event_referral_expirations` | Paldi challenge: marks participants WON or BLOCKED once their deadline passes. | Yes. |
| Daily (`30 1 * * *`) | `expire_subscriptions --apply` | Only while Admin → Settings → Security → *Enforce subscription expiry* is ON: marks ended subscriptions `expired` and lists those due in 7 days. Does nothing while OFF (the default). | Yes. |
| Daily (`0 3 * * *`) | `backup_database --tag daily --retention 7` | Timestamped DB backup, keeps the last 7. | Yes. |
| Weekly, dry run (`0 9 * * 1`) | `recover_orphaned_payments --days 14` | **Lists only**: captured registration payments that never activated an agent, and possible double charges. Read the log; run with `--apply` by hand after checking. | Dry run changes nothing. |

## One-time after the 2026-10-01 audit deploy

1. Migration `agents.0033_index_razorpay_lookup_columns` runs automatically on
   deploy (the deploy script backs up the DB first).
2. Run `recover_orphaned_payments --days 60` (dry run). For each listed agent
   check Razorpay, then run it again with `--apply`. Payments flagged as a
   possible double charge are never auto-activated; refund those in Razorpay.
3. Run `retry_missing_invoices --days 60` (dry run), then with `--apply`.
4. Add the cron jobs above.

## Manual-only commands

`restore_database`, `repair_imported_agent_data`, `unify_plan_display_names`,
`import_blacklisted_agents`, `seed_*`, `test_email`, `verify_production_env`:
run by hand, never from cron.
