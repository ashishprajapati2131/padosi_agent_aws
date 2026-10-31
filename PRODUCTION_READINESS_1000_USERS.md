# Production Readiness Report: Ready for 1,000 users?

Audit date: 2026-11-01. Method: read-only code audit, with no files changed and no production access. The top findings were re-checked by hand.
Not visible in code: hosting-panel backups, Passenger worker count, MySQL connection limits, Razorpay dashboard webhook events, and provider billing alerts.

## Scorecard

| # | Check | Verdict | One-line reason |
|---|---|---|---|
| 01 | Race conditions | 🟡 PARTIAL | The payment path is locked properly. The leaderboard, view counter and OTP attempts are not. |
| 02 | N+1 queries | 🟡 PARTIAL | Main search is fine. The leaderboards and some admin pages run one query per row. |
| 03 | Error tracking | 🟡 PARTIAL | Sentry is wired up, but only works if `SENTRY_DSN` is set in production. |
| 04 | Rate limits | 🟡 PARTIAL | Login and forgot-password are covered. The card-lead form, contact form and search are not, and FastAPI limits are per process. |
| 05 | Background jobs | 🟡 PARTIAL | Well designed for Passenger. A failed welcome email is never retried, and job claims can run twice. |
| 06 | Spend alerts | 🔴 NOT READY | There is no daily cap or budget alert anywhere: LLM, Brevo and leads are unlimited. |
| 07 | Rollback | 🟡 PARTIAL | A rollback script exists, but it targets the wrong commit, skips health checks and doesn't reverse migrations. |
| 08 | Live database | 🟡 PARTIAL | Tests use SQLite, which is good. The connection pool, unguarded bulk commands and env override are risks. |
| 09 | Webhooks | 🟡 PARTIAL | The main Razorpay webhook is excellent. The WhatsApp-bot webhook is 🔴 dangerous. |
| 10 | Backups | 🔴 NOT READY | Backups only run before migrations, live on the same disk, can fail silently, and media is not backed up. |

**Overall: NOT READY yet.** Fix the 🔴 items in "Fix NOW" below first. Each of them is a small change.

---

## Fix NOW (security or money, verified by hand)

1. **The WhatsApp-bot Razorpay webhook activates without checking the event type**: `apps/wa_agent_bot/views.py:282-342`
   It verifies the signature, but it **never checks `event`** and has no amount check. A signed `payment_link.expired`, `payment_link.cancelled` or `refund.processed` event that carries `notes.subscription_id` could activate a subscription **for free**. It also always sets `pending_approval`, so it can demote an already-active agent.
   → Fix: accept only `payment_link.paid`, `order.paid` and `payment.captured`, then compare the amount with `sub.amount`.

2. **Account-deletion OTP: expired codes are accepted**: `fastapi_app/routers/account_deletion.py:256-265`
   The expiry `HTTPException` is raised inside `try: ... except Exception: pass`, so the error is swallowed. The attempt counter is also a read-modify-write in JSON with no lock, so parallel requests get far more than 5 guesses.
   → Fix: parse only inside the `try`, and do the expiry comparison outside it. Lock the row with `with_for_update()`.

3. **Backups can fail silently and are kept on the same server**
   - `scripts/deploy_godaddy.sh:100`: `|| echo "WARNING: Backup failed, continuing..."`. Migrations still run when the backup fails.
   - `apps/agents/management/commands/backup_database.py:60`: prints ERROR but exits 0.
   - `backup_database.py:103-104`: if `mysqldump` fails, it falls back to `dumpdata`, which **leaves out every unmanaged table** (users, admins, pincodes and others).
   - Backups go to `BASE_DIR/backups/` on the same disk. They are not encrypted, there is no offsite copy, and `media/` has no backup at all.
   - `docs/CRON_JOBS.md`: there is no scheduled daily backup.
   → Fix: make the backup command raise `CommandError` and change deploy to `|| exit 1`. Add a daily mysqldump plus a copy of `media/` to offsite storage (S3, Backblaze or Google Drive). Do one restore drill.

4. **Spend caps**
   - Chatbot: the only limit is 20 per minute per IP, which allows **28,800 messages per day**. Each message can trigger up to 3 LLM calls with about 15k input tokens of history.
   - Bio generator (`bio_generator.py:26`): no per-user limit.
   - Card-lead form (`apps/agents/views/qr.py:542-669`): no IP limit. Each submission sends a Brevo email, an FCM push and a WhatsApp alert.
   → Fix: add a daily cache counter per IP (for example 100 chatbot messages and 10 leads), a global daily ceiling that disables the bot, and billing alerts in the Groq, Gemini and Brevo consoles.

5. **`SENTRY_DSN`**: it is blank in `.env.example:63`. Run this on the production server:
   ```bash
   python manage.py verify_production_env
   ```
   If it reports Sentry as disabled, set the DSN. Without it, nobody gets alerted when checkout returns a 500.

---

## 01 · Race conditions: PARTIAL
✅ Done well:
- Payment activation uses `select_for_update` plus an early return when already completed (`registration.py:3044`).
- Promo usage is incremented with `F()`.
- Reward `get_or_create` is backed by `unique_together`.
- Search counters use `F()` updates.

❌ Issues:
- `referral_championship/.../qualification_service.py:123` → `leaderboard_service.py:33-45`: the leaderboard refresh runs **inside the payment transaction**. That is about 3,000 writes per referred payment while holding locks. Concurrent payments can deadlock, the savepoint swallows the error, and the referrer **silently loses credit**.
  → Fix: `transaction.on_commit(...)` plus `bulk_update`.
- `agents/views/qr.py:462` and `dashboard.py:1043`: `get_or_create(agent, view_date)`, but `agent_profile_views` has **no unique index**. Two simultaneous views create a duplicate row. After that, `MultipleObjectsReturned` is swallowed and views stop counting for the rest of the day.
  → Fix: a migration adding `unique_together=('agent','view_date')`.
- Promo `max_uses` is checked at checkout but only incremented at payment, so a limited promo overshoots under load.
- `mobile` is not unique (`registration.py:1830`), so two concurrent sign-ups with the same number both succeed. Low risk.
- `google_review.py:244` and `admin_panel/views/qr_files.py:207` use `clicks += 1; save()`, which loses updates. → Use `F()`.

## 02 · N+1 queries: PARTIAL
✅ Done well:
- Directory search uses `select_related`/`prefetch_related`.
- FastAPI search paginates in SQL.
- The admin agent list uses raw SQL with LIMIT.

❌ Issues:
- Leaderboards run `agent.serviceableCities.first()` once per row (`leaderboard_service.py:75` and `event_referral/services/public_leaderboard.py:16`). City has no ordering, so `.first()` re-queries even when the relation is prefetched.
  → Use `next(iter(agent.serviceableCities.all()), None)`.
- `home/views/pages.py:689`: `list(query)` loads all matching agents plus 5 prefetches to show 5 cards. It's fine now but grows linearly.
- Admin pages (`insurance_approvals.py:51-80`, `insurance.py:63`, `advanced.py:56`) run one query per row. Low impact.

## 03 · Error tracking: PARTIAL
✅ Done well:
- Sentry plus a LoggingIntegration with `event_level=ERROR` (`settings.py:421-442`).
- `DEBUG` defaults to False, `500.html` exists, and the file log rotates.

❌ Issues:
- Sentry only runs when `SENTRY_DSN` is set.
- The `ErrorLog` middleware has no alerting, and its write is wrapped in `except: pass` (`admin_panel/middleware.py:910`).
- Silent `except: pass` in the payment path:
  - `registration.py:3370` and `:3391` silently fall back to the non-campaign price.
  - `:1651` silently turns off the signup rate limit if the cache errors.
  → Add `logger.exception` to each of these.

## 04 · Rate limits: PARTIAL
✅ Done well:
- Spoof-safe client IP detection (the trusted-proxy rule takes the right-most public hop).
- Login: per-IP limit plus 10 failures per email in 15 minutes.
- Forgot-password: 10 per IP and 3 per email per hour.
- Chatbot: 20 per minute.
- Lead capture: limit backed by the database.

❌ Issues:
- FastAPI rate limits are **in-memory per process** (`fastapi_app/middleware/rate_limiter.py:22`, `auth_service.py:13`). With N Passenger processes, the real limit is N times higher.
- FastAPI `/v1/agents/forgot-password` has no per-email limit, and it returns "account not found", so it can be used to find which emails have accounts.
- No limit at all on the card-lead form (`qr.py:542`), the contact form (`pages.py:98`) or public search.
- The chatbot cross-origin check is skipped when the `Origin` header is missing (`chatbot/views.py:85`).
- The cache is file-based: `add`/`incr` are not atomic. The Redis branch in `settings.py:211-219` would probably break, because the `redis` package is missing and `IGNORE_EXCEPTIONS` is a django-redis option only.

→ Fix: reuse the existing cache-counter pattern from `allow_forgot_password_request` for these endpoints.

## 05 · Background jobs: PARTIAL
✅ Done well:
- Jobs are triggered by traffic and claimed with `cache.add`.
- The hourly `retry_missing_invoices` job recovers work lost on process restarts.
- Post-payment work runs `on_commit`.
- Chromium is limited to one at a time with a file lock.

❌ Issues:
- The welcome email and Sheet sync are retried only when the invoice is missing. If the invoice exists but the email failed, **the email is lost for good** (`post_payment.py:84`).
- `cache.add` on the file cache is not atomic, so two requests can claim the same job and send duplicate emails (`background_jobs.py:78,157`).
  → Use MySQL `GET_LOCK`, which is already used at `registration.py:2015`.
- Every public search starts a new DB-writing thread (`pages.py:989`). Crawler traffic means unbounded threads and connections.

## 06 · Spend alerts: NOT READY
✅ Done well:
- LLM `max_tokens=600`, a 10-second timeout and `max_retries=0`.
- History is limited to 30 messages and input to 2,000 characters.
- Tokens are logged in `LatencyLog`.
- WhatsApp view alerts go out once per agent per day.
- There is no SMS provider, so there is no OTP-bombing cost.

❌ Issues:
- No daily cap, budget or alert exists anywhere. The likely failure is that the Groq/Gemini quota runs out and **the chatbot goes down for everyone**.
→ See "Fix NOW" #4.

## 07 · Rollback: PARTIAL
- Deploy runs `git pull` in place (`deploy_godaddy.sh:43`). There are no release folders.
- `rollback_godaddy.sh:25-36` falls back to `HEAD~1` after a successful deploy, which is wrong when one push had several commits. It also doesn't reinstall requirements or reverse migrations.
- `deploy.yml:95-129` retries a failed deploy 3 times, which re-runs `migrate`.
- `deploy.yml:136-142`: the post-deploy check only greps one page. It doesn't call `/health/`, and failures don't trigger a rollback.
- **Irreversible migrations** (`RunPython` with `noop` reverse):
  - `admin_panel/0013`
  - `agents/0025`
  - `event_referral/0005` and `0007`
  - `home/0008`
  - `wa_agent_bot/0002`
- **Destructive migrations:**
  - `home/0003` (about 30 removals)
  - `wa_agent_bot/0001` (drops tables, with an empty reverse)
- MySQL DDL is not transactional, so a half-failed migration leaves the schema partly changed.

→ Fix:
1. Write `tmp/.previous_deployed_commit` during deploy and roll back to it.
2. After deploy, run `curl -f .../health/` and roll back automatically if it fails.
3. Drop a column one release after the code stops using it.

## 08 · Live database: PARTIAL
✅ Done well:
- CI tests run on in-memory SQLite with dummy credentials.
- The local `.env` points at a local host with a Razorpay test key.

❌ Issues:
- `settings.py:37` loads `.env` with `override=True`, but `fastapi_app/config.py:17` uses `override=False` and also reads `MYSQL*` variables. Django and FastAPI could end up on different databases.
- Pool size: `CONN_MAX_AGE=60`, plus SQLAlchemy `pool 5 + overflow 10` **per Passenger process** (`fastapi_app/database.py:21`). On shared MySQL this means "Too many connections" at around 1,000 users.
  → Set `DB_POOL_SIZE=2` and `DB_MAX_OVERFLOW=3`.
- Tests force every model to be managed, so **drift between the unmanaged models and the real MySQL schema is never tested**.
- MySQL trigger `admin_panel/0002` hard-codes the column list for `agents`. Changing that table can make agent deletion fail.
- Unguarded bulk commands:
  - `repair_imported_agent_data` applies changes by default.
  - `seed_homepage` runs `.all().delete()` with no confirmation.
  → Make `--apply` opt-in and add a confirm prompt.
- A single DB user both serves the app and runs migrations, so it needs ALTER, DROP and TRIGGER rights.

## 09 · Webhooks: PARTIAL
✅ The main `/razorpay-webhook/` (`registration.py:4524-4633`) is excellent:
- HMAC check with no DEBUG bypass.
- Fulfilment happens in the webhook.
- Idempotent, with a row lock.
- Returns 503 to make Razorpay retry when the order isn't found yet.
- Server-side amount check.
- Full refunds are handled with locks.
- `recover_orphaned_payments` covers lost callbacks.

❌ Issues:
- The WhatsApp-bot webhook: see "Fix NOW" #1.
- **Event and insurance orders have no webhook fulfilment** (`registration.py:4595`). If the tab closes after payment, the user is paid but not registered, and `recover_orphaned_payments` only scans `AgentSubscription`.
- An amount mismatch returns 400 (`registration.py:4612`), so Razorpay retries for 24 hours and may disable the endpoint.
  → Return 200 and flag the payment for review.
- `wa_agent_bot/views.py:153`: incoming WhatsApp messages are not de-duplicated, so a redelivered message advances the bot twice.

## 10 · Backups: NOT READY
See "Fix NOW" #3. Also:
- `backup_system.py:54` passes the password in the command line (`--password=`), so it shows up in the process list.
- Its zip files are never pruned, and `restore_database --latest` ignores them.

## Other security notes noticed in passing
- `apps/admin_panel/views/system.py:241-242`: the cron token falls back to `SECRET_KEY[:24]` and is accepted from a `?token=` query parameter, so part of `SECRET_KEY` can leak into access logs. → Set `CRON_TRIGGER_TOKEN` and accept the header only.
- `deploy.yml:106`: SSH runs with `StrictHostKeyChecking=no`. → Pin the host key in a GitHub secret.

## Not checked
- Template `{% for %}` loops (possible N+1).
- Agent-dashboard leads views.
- Insurance-portal payment internals.
- Which events are actually subscribed in the Razorpay dashboard. This decides whether the WhatsApp-bot webhook issue can be exploited right now.
- Real production config.

---

## Fix status (2026-11-01)

Full suite after the fixes: `manage.py test apps fastapi_app` ran 1026 tests, OK (2 skipped). `check` is clean and no migrations are pending.

| # | Status |
|---|---|
| 01 Race conditions | ✅ Profile-view unique index (migration `agents/0040` merges duplicates first) · leaderboard refresh runs `on_commit` with `bulk_update` · click counters use `F()`. Also fixed a hidden bug: `timezone.localdate()` meant card views were never counted. |
| 02 N+1 | ✅ Leaderboards and the 3 admin pages fixed. |
| 03 Error tracking | ✅ Silent `except: pass` blocks now log. ⚠️ You still need to set `SENTRY_DSN` in production. |
| 04 Rate limits | ✅ Card-lead form, contact form and FastAPI forgot-password (no account enumeration) are limited · FastAPI limiter now uses the shared cache · chatbot Origin/Referer check · Redis branch fixed. |
| 05 Background jobs | ✅ Job claims use MySQL `GET_LOCK` · search analytics threads are de-duplicated · a failed welcome email is now logged. ⏳ Automatic re-send needs a new DB field (your call). |
| 06 Spend | ✅ Chatbot caps: 100 per IP per day and 5000 per day globally, with an alert · bio generator capped at 10 per agent per day (env vars in `.env.example`). ⚠️ Set billing alerts in the Groq, Gemini and Brevo consoles. |
| 07 Rollback | ✅ Deploy records the previous commit · rollback uses that record · `/health/` check after deploy rolls back automatically · retries only on SSH connection failure. |
| 08 Live DB | ✅ FastAPI pool reduced to 2+3 · `repair_imported_agent_data` is a dry run unless `--apply` · `seed_homepage` needs `--yes`. ⚠️ The env override mismatch (Django `override=True` vs FastAPI) is not changed; check it on the server. |
| 09 Webhooks | ✅ WhatsApp-bot webhook: event allowlist, amount and capture checks, no demotion, message de-duplication · main webhook returns 200 and an alert on amount mismatch. ⏳ Event/insurance order fulfilment from the webhook is still open (needs an events.py refactor). |
| 10 Backups | ✅ A failed backup aborts the deploy · no incomplete `dumpdata` fallback on MySQL · daily backup job keeps 14 · password passed via env. ⚠️ An offsite, encrypted copy and backup of `media/` need a destination you choose. |
| Extra | ✅ Expired deletion OTP fixed · OTP row lock · cron token no longer uses a `SECRET_KEY` fallback · deletion route uses the correct client IP · contact form no longer logs PII · mobile bio returns 429 at the cap. |

### Update: event/insurance webhook (2026-11-01)
- ✅ Event orders: the webhook, the browser callback and `recover_orphaned_payments --apply` all go through one idempotent function, `fulfil_event_registration` (row lock, capture check, amount check, no duplicate emails). Invariant 9: an existing order id is never overwritten.
- ✅ Insurance bulk checkout (`checkout_online_success`) now requires a captured payment (invariant 10). Test: `apps/insurance/test_bulk_checkout_capture.py`.
- ⏳ Insurance single-agent webhook: the fulfilment code first has to be moved out of `handle_payment_success`. Bulk cart needs a server-side cart table (migration).
- ⚠️ `/events/` signup flow can't be reached: `urls_events.py` declares `register/` and `plans/` twice, so `register` and `select_plan` never run. Enabling it is a product decision.
- ⚠️ Behaviour change: a new event agent's first password is their mobile number (invariant 3), not a random password.
- Full suite: 1033 tests OK (2 skipped).
