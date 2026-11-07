# Admin Panel Audit — 2026-11-07

**Scope:** `apps/admin_panel/` (~30K Python lines: 53 view modules, 25 model files, 17 services, `urls.py`, `middleware.py`, `context_processors.py`) and `templates/admin/` (96 templates, ~37K lines).
**Method:** four parallel read-only audits (security, bugs, performance, structure). The top findings were then re-checked in code by hand; those are marked ✅. No code was changed and no tests were run.

## Headline numbers

| Area | Critical | High | Medium | Low |
|---|---|---|---|---|
| Security | – | 2 | 6 | 7 |
| Bugs / data integrity | 1 | 4 | 15 | 5 |
| Performance | – | 9 | 9 | 5 |
| Structure / scalability | – | – | 18 findings (see §4) | – |

**Fix first (this week):** S1, S2, B1, P1, B3, B4, B5, S4. One staff account can currently become super admin (S1), and an admin click can hand out a free paid plan (B1).

---

## 1. Security

The core gate is solid. `AdminPermissionMiddleware` denies by default on exact `url_name`, every raw SQL query is parameterised, CSV/XLSX exports use `safe_csv_writer`, and the session cookie is HttpOnly/Secure/Lax with token rotation on login. **No unauthenticated admin view was found.** The problems are privilege escalation *between* staff and super admin.

| # | Sev | Where | Issue | Fix |
|---|---|---|---|---|
| S1 ✅ | **High** | `views/agents.py:756-799` → `views/dashboard.py:950` → `templates/admin/dashboard.html:380` | **Stored XSS → super-admin takeover.** `update_plan` (needs only the `agents` permission) stores any free-text `selected_plan`. The dashboard dumps the plan names with `json.dumps(...)` and renders them with `{{ plan_keys_json\|safe }}` inside `<script>`, and `json.dumps` does not escape `</script>`. A staff admin sets the plan to `</script><script>…create admin…</script>`; the next super admin who opens the dashboard runs it. | Render with `json_script` / `safe_json`. Reject plan names outside the allowed list in `update_plan`. |
| S2 ✅ | **High** | `views/settings.py:1002-1015` | Anyone with `email_templates` can **write raw Django template source** to `templates/pdf/invoice.html` and the email templates on disk. The invoice is rendered with full ORM objects and passed through xhtml2pdf, so this can leak related data and possibly allow `file://` reads or SSRF (UNVERIFIED). An empty `file_content` writes `None`, which crashes. Edits are also lost on deploy. | Make it super-admin only, store templates in the DB, and render them in a restricted engine with plain dicts. |
| S3 | Med | `views/agents.py:747` | `update_plan` lets staff put any agent on Professional/Exclusive with ₹0. That bypasses the super-admin-only `mark_payment`. | Require `_is_super_admin` for paid plans. |
| S4 ✅ | Med | `admins.py:203` (`admins_destroy`), `qr_files.py:181`, `settings.py:559,577,725` | **State-changing GET requests.** Because the cookie is SameSite=Lax, a link click by a super admin can delete another admin. | `@require_POST` on all five. |
| S5 | Med | `views/users.py:127-200` | The `users` permission can change the password, email and role of any user, including distributors. On a validation error, line 188 saves `request.POST.dict()`, **including the plaintext password**, into the session. | Make password and email changes super-admin only; strip password fields before saving `form_old`. |
| S6 | Med | `dashboard.py:171-205, 378-384` | Lockout is per IP only (5 per hour). MFA is off by default. Unknown emails return before bcrypt runs, which allows email enumeration by timing. | Add per-email throttling, turn on `ADMIN_MFA_ENABLED` in production, and run a dummy bcrypt check for unknown emails. |
| S7 | Med | `admins.py:186-196` | Resetting a password leaves existing sessions valid for 7 days. There is no idle timeout. | Delete that admin's `user_sessions` rows on password change; add idle expiry. |
| S8 | Med/Low | `views/contacts.py:276-281` | Contact-form `name`/`subject` go unescaped into the HTML of the admin's reply email, which enables phishing in a branded email. | `escape()` every value. |
| S9 | Low | `analytics.html`, `finance.html`, `revenue/dashboard.html`, `free_trial/index.html`, `settings/hero_section.html`, `content/_manage_agent_chrome.html` | Same `json.dumps\|safe` pattern as S1. Not exploitable today, but it breaks CLAUDE.md rule 5. | Switch to `safe_json`. |
| S10 | Low | `dashboard.py:442` | Logout is `csrf_exempt`, so another site can force a logout. | Remove the exemption. |
| S11 | Low | `views/system.py:399-466` | The maintenance-jobs gate checks `request.user.is_staff`, which is never true for admin sessions, so the endpoint is broken for everyone. It also takes the cron token in the query string and runs on GET. | Gate on `_is_super_admin`, require POST, and read the token from a header. |
| S12 | Low | 13 sites, e.g. `agents.py:1021`, `system.py:388` | Exception text, including mysqldump stderr, is returned to the browser. | Return a generic message and log the detail. |
| S13 | Low | `dashboard.py:236`, `sessions.py:126` | Session tokens are stored in plaintext. Staff with `sessions` can revoke super-admin sessions. | Store a SHA-256 of the token; block revoking super-admin sessions. |
| S14 | Low | `qr_files.py:84` | Public download codes use `random.choices`, which is not a cryptographic generator. | `secrets.choice`. |
| S15 | Low | `services/amfi_scraper.py:12-28, 219-230` | A substring URL check with redirects followed allows SSRF to any host. | Allowlist on `urlparse().hostname`; set `allow_redirects=False`. |

---

## 2. Bugs and data integrity

| # | Sev | Where | Bug → failure | Fix |
|---|---|---|---|---|
| B1 ✅ | **Critical** | `views/wa_bot_admin.py:446-466` | "Resend credentials" calls `activate_agent_subscription_after_payment()` on the agent's **newest** subscription. If that row is an unpaid `pending` checkout, the call **marks it completed and active for 365 days**, which is a free paid plan. If the row is already paid, the function returns "Already activated" and **sends nothing**, yet the view still reports success. | Only act on `payment_status='completed'` rows, and call a pure "send credentials" function instead of the activation function. |
| B2 | High | `agents.py:856-912` | The admin email edit rewrites `agents.email` via raw SQL without the `_email_taken_by_other_login` check and without syncing `auth_user`. Another login can then open this agent's dashboard (breaks CLAUDE.md invariant 6). There is no `atomic`. | Reuse the check from `dashboard.py`, sync `auth_user`/`users`, and wrap the writes in `atomic`. |
| B3 | High | `payment_reconcile.py:496-528, 597` | Find-or-create of the subscription has no lock, and `razorpay_order_id` is not unique. Two "Execute" clicks give double activation, two invoices and double referral credit. | `select_for_update` or a cache lock keyed on `order_id`, or a unique constraint. |
| B4 | High | `delete.py:92-134` | Agent hard-delete continues when the backup INSERT fails, and runs outside a transaction. `has_payments` ignores `pending` rows that hold captured orders. | Abort if the backup fails, wrap in `atomic`, and treat any real `razorpay_order_id` as a payment. |
| B5 | High | `subscriptions.py:117-142` | Staff can hard-delete **paid** subscriptions. That destroys GST and payment records (invariant 9). | Refuse when `completed`, or soft-delete. |
| B6 ✅ | Med | `delete.py:180` | The promo branch selects `discount_percent, uses_count`, but the real columns are `discount_value, times_used`, so **every promo delete returns a 500**. | Fix the column names. |
| B7 | Med | `insurance_approvals.py:144-148, 170-173`; `account_deletion.py:136-143, 225-232` | `try/except: pass` around DB calls inside `atomic()`. Any DB error then turns into `TransactionManagementError` and the whole approval rolls back. | Nested `with transaction.atomic():` (savepoint). |
| B8 | Med | `account_deletion.py:229` | Re-activation always sets `active` and makes the card visible, skipping payment and approval for agents who were pending. | Store the previous status and restore it. |
| B9 | Med | `account_deletion.py:127-128` | Falls back to matching by mobile, so a request carrying someone else's number terminates the wrong agent. | Require a linked agent or an email match. |
| B10 | Med | `agents.py:791-806` | `update_plan` overwrites `selected_plan` on a **paid** row, which moves past revenue to another plan. It creates "completed" ₹0 rows, and `int(agent_id)` sits outside the try (500 on bad input). | Change `plan_type` only; never touch paid rows. |
| B11 | Med | `finance.py:364-379` | `mark_payment` skips the shared activation path (plan, superseded rows, referral credit). Un-completing leaves the agent `active`. | Route through `_activate_paid_subscription`. |
| B12 ✅ | Med | `revenue.py:53-62` | `total_revenue` = professional + starter + trial only. **Exclusive plan revenue is missing**. | `SUM(registration_amount) WHERE payment_status='completed'`. |
| B13 | Med | `subscriptions.py:22, 69-98` | Counts pending, failed and superseded rows; `est_revenue` uses hard-coded 999/499 prices. | Filter `completed`+`active`; read prices from `pricing_config`. |
| B14 | Med | `finance.py:101,272,288`, `revenue.py:28,71`, `free_trial.py:144,384` | IST-naive columns compared with `UTC_TIMESTAMP()`. Expired subscriptions still count in MRR for 5.5 h. | Pass Python `datetime.now()`, as `dashboard.py:757` already does. |
| B15 | Med | `broadcast.py:102-141` | Sends one email per agent synchronously inside the request; all errors are swallowed. The request times out partway, no record is saved, and a retry re-sends to the first batch. | Use a background job (as `wa_bot_broadcast` does) and log failures. |
| B16 | Med | `broadcast.py:25-28` vs `notify.py:165-172` | The "Starter" target is defined differently on each page and misses `basic` agents. | One shared target query. |
| B17 | Med | `invoices.py:465-469` | A fixed ₹500 promo is stored as 500%; values ≥1000 overflow `Decimal(5,2)` and return a 500. | Use the value only when `discount_type=='percentage'`. |
| B18 | Med | `invoices.py:442-513` | Money handled as `float`, negative/NaN accepted, no dedupe on `razorpay_payment_id`, so a resubmit creates a duplicate invoice. | `Decimal` with range checks; reject a payment_id already used. |
| B19 | Med | `distributors.py:174-186` | `users` and `referral_codes` INSERTs are not atomic, which leaves orphan users. | `atomic()`. |
| B20 | Med | `plans.py:120` | The slug is regenerated on every plan rename, so toggles and the FastAPI mapping can lose the plan (UNVERIFIED). | Freeze the slug after creation. |
| B21 | Low | `agents.py:351-376` | A double-clicked approve sends two WhatsApp messages. | `UPDATE … WHERE status=old` and check `rowcount`. |
| B22 | Low | `invoices.py:32`, `free_trial.py:723`, `referrals.py:380`, `content.py:846`, `finance.py:350` | Unguarded `int()` on request input returns a 500. | Small `parse_int(default)` helper. |
| B23 | Low | `notify.py:218`, `broadcast.py:169` | Reports "sent" even when FCM is not configured. | Return the real sent count. |
| B24 ✅ | Low | `urls.py:582` and `:724` | **Duplicate URL name** `admin_toggle_wa_bot_service` on two different views. | Rename one or delete it. |
| B25 | Low | `insurance_approvals.py:89-112` | `is_pending()` checked without a lock, so a double POST processes twice. | `select_for_update` inside `atomic`. |

---

## 3. Performance

| # | Impact | Where | Issue | Fix |
|---|---|---|---|---|
| P1 ✅ | **High (DoS)** | `middleware.py:286` | The WAF's SSTI regex `{{\s*[\s\S]*\s*}}` is greedy and runs on **every public request**. Measured: a 20 KB body takes ~3.2 s; the time grows quadratically, so a 1–2 MB POST can tie up a worker for minutes or longer. | Use `\{\{[^}]{0,200}\}\}`, precompile patterns at module level, and scan only the first 8 KB. |
| P2 ✅ | High | `services/feature_flags.py:245-274` via `apps/home/context_processors.py:206` | Every public page does ~20 file-cache reads, because each one unpickles the whole site-settings dict. `FEATURE_FLAGS_CACHE_KEY` is **deleted but never read**, so the computed flags are never cached. | Cache the computed dict under that key; invalidation already exists. |
| P3 | High | `settings.py:250-259` + `middleware.py:61,85` | FileBasedCache plus a per-visitor-IP `waf_ip_blocked_<ip>` write every 60 s. Each `set()` globs the whole cache directory (up to 5000 files), and culling evicts `site_settings_all`. | Move to Redis or the DB cache (a branch already exists), or keep one cached blocked-IP set. |
| P4 | High | `views/dashboard.py:86-165`, `middleware.py:143,522,552`, every view | Admin auth is resolved 3–4 times per request, about **7–10 queries per admin page** just for auth. | Resolve once in the middleware, store it as `request.admin`, and read that everywhere. |
| P5 | High | `broadcast.py:97-140` | Sequential Brevo calls inside the request (20 s timeout each). | Background job and batch API. |
| P6 | High | `agents.py:1033-1055, 1227-1352` | The pending-registrations query has 6 correlated subqueries per row, **no LIMIT**, a Python merge and sort, and only then pagination. | Paginate in SQL, as `agent_list` already does. |
| P7 | High | `agents.py:1151-1224` | The approvals page and `missing_irdai_agents` are unpaginated. | Paginate. |
| P8 | High | `find_agent_locator.py:686-748` | Scans every active agent in Python, with 2 queries per agent for rating and 1 per pincode. `_count_matching_agents` builds the whole list just for `len()`. | `annotate(Avg)`, bulk-load pincodes, bounding-box SQL pre-filter. |
| P9 | High | `pincode.py:449-470` | The pincode export loads the whole table (~150K rows) into memory. | `.values_list().iterator()` + `StreamingHttpResponse`. |
| P10 | Med | `dashboard.py:464-835` | About 20 uncached queries; `MONTH()/YEAR()/DATE()` predicates can't use indexes. | Date ranges, one `SUM(CASE…)`, cache for 60–300 s. |
| P11 | Med | `context_processors.py:76-245` | 16 COUNTs every 30 s for the sidebar badges, with no stampede protection. | TTL of 2–5 min; invalidate on write. |
| P12 | Med | `export.py:112-318` | Every export uses `fetchall()` and a buffered response. `export_agents` joins **all** subscriptions, so agents appear more than once. | Stream; join only the latest subscription. |
| P13 | Med | `pincode.py:328-345` | `list(stream_csv())` defeats the generator; the import runs synchronously. | Iterate directly; run in the background. |
| P14 | Med | `pincode.py:146-156` | 5 full-table aggregates per page view. | Cache them; invalidate on import. |
| P15 | Med | `pincode_heatmap.py:136-186, 290` | N+1 lookups; `message__icontains` does a full scan. | Bulk `__in`; cache. |
| P16 | Med | `find_agent_locator.py:152+` | Up to 4 sequential geocode calls plus `sleep(1)`, so 20 s+ worst case. | Drop the sleep; cache misses. |
| P17 | Med | `apps/agents/models.py`, `contact_submission.py` | No declared indexes on `agents.created_at/agent_pincode/plan_type`, `agent_subscriptions.expires_at/payment_status`, `agent_leads.lead_status`, `contact_submissions.status/created_at` (UNVERIFIED against the live DB). | Run `SHOW INDEX`, then add composite indexes. |
| P18 | Med | `system.py:381-396` → `backup_system.py:67` | `mysqldump` runs inside the request with no timeout. | Background job with `timeout=`. |
| P19–23 | Low | `middleware.py:405, 252-305, 490`, `context_processors.py:65, 289` | Synchronous alert email, JSON re-parsing per request, extra queries, and a 30 s stale-permission cache. | See the inline notes in the code. |

---

## 4. Structure, clean code and scalability

### What's wrong (evidence)

1. **Logic sits in views.** `views/` has 19,540 lines against 3,042 in `services/`. 336 ORM calls and 109 raw-SQL calls live in views. 48 functions are over 100 lines; the largest are `ThreatMonitorMiddleware.__call__` (317), `get_required_permission` (316), `admin_badge_counts` (291), `finance.index` (277) and `reconcile_inspect_payment` (257).
2. **Auth check copy-pasted 265 times** ✅ (`_get_admin_from_session(request)` in 51 files) with four different failure responses, even though the middleware already enforces auth. `@admin_login_required` is used only twice.
3. **Views used as a library.** Other apps import `views.dashboard._get_admin_from_session` 52 times, plus `views.agents._build_queue_query`, `views.finance.mark_payment` and others. This risks import cycles.
4. **Duplicated helpers.** `_log_activity` is defined twice; CSV responses are hand-built in 3 places; there are 21 `Paginator` copies with page sizes of 15/20/25/50; 327 hand-built `JsonResponse({'success'…})`; POST enforcement is mixed (111 decorator uses vs 79 inline checks).
5. **Wrong model ownership.** `models/agent.py`, `city.py` and `agent_subscription.py` are re-export shims. `models/event.py` maps the same `events` table as `apps/agents.Event` with different fields and is unused, so delete it. Referral models live under admin, but 123 imports from other apps depend on `admin_panel`.
6. **Adding a module means editing 4 places:** `admins.get_permissions_list`, the 316-line `url_name→perm` dict in `middleware.py:713`, the `perm→route` map at `:1030`, and ~45 `{% if … in admin_permissions %}` checks in `base.html`.
7. **`middleware.py` (1,137 lines) holds 5 unrelated middlewares** (WAF, IP whitelist, session isolation, RBAC, exception logger) plus IP helpers that 17 other places import.
8. **`urls.py`:** 760 lines, 307 `path()` calls, 0 `include()`, no namespace, 24 route names without the `admin_` prefix, and a stale docstring.
9. **Templates:** 9,652 lines of inline JS and 3,709 of inline CSS. Pagination markup is repeated in 30 files and modals in 23; `getCookie` is defined 6 times and toast helpers 3 times. There are only 4 partials.
10. **Magic status strings:** `'active'` ×52, `'completed'` ×19, and only 6 `TextChoices` in the whole app.
11. **Generic delete endpoint** (`delete.py:30`, 182 lines of raw SQL branching on a `model` value from POST).
12. **Tests:** 26 flat `test_*.py` files. pytest collection fails on 24 of them (no pytest-django config; use `manage.py test`). There are **no tests** for `admins` (the RBAC editor), `referrals`, `coming_soon`, `advanced`, `notify`, `promo_codes`, `users`, `broadcast`, `plans`, `subscriptions` or `security`.
13. **Dead code:** `services/invoice_storage.py` and `services/playwright_manager.py` (0 references ✅), and `models/event.py`.
14. **CLAUDE.md is out of date about the admin panel.** It says to use `@admin_required`, but no view uses it; the middleware does the gating. It says `AdminIpWhitelistMiddleware` is commented out, but it is active at `settings.py:153`. It also says roles are `superadmin`, while the code uses `'super'`.
15. **Hard-coded config:** page sizes, badge colours and the `/admin` and `/padosi-admin` prefixes are repeated in `middleware.py:512`, `context_processors.py:30` and `urls.py`.

### Target structure

```
apps/admin_panel/
  apps.py            # ready(): autodiscover modules -> registry
  conf.py            # ADMIN_PREFIXES, PAGE_SIZE, ...
  registry.py        # AdminModule(key, label, icon, nav_group, default_route, badge=callable)
  auth.py            # get_admin(request), require_super  (moved out of views/dashboard.py)
  core/
    responses.py     # json_ok / json_err
    pagination.py    # paginate(request, qs)
    exports.py       # csv_response (wraps spreadsheet_safety)
    activity.py      # log_action(request, ...)
    parsing.py       # parse_int / parse_decimal
  middleware/
    security.py  ip_whitelist.py  session_isolation.py  rbac.py  exceptions.py
  modules/
    agents/  finance/  referrals/  free_trial/  content/  settings/ ...
      __init__.py    # MODULE = AdminModule(...)
      urls.py  views.py  services.py  selectors.py  tests/
  models/            # admin-owned only: Admin, ActivityLog, ErrorLog, ApiLog...
  services/          # cross-module integrations: brevo, fcm, cloudflare, sheets
  urls.py            # ~20 lines: auth routes + include() per registered module
templates/admin/
  base.html          # sidebar rendered from the registry
  components/        # pagination, modal, filter_bar, table, empty_state
static/admin_panel/  # admin.js (csrfFetch, toast), admin.css, <module>/*.js
```

### Recipe: adding a new admin module (after the migration)

1. `apps/admin_panel/modules/coupons/__init__.py` → `MODULE = AdminModule(key="coupons", label="Coupons", nav_group="Finance", default_route="admin_coupons_index", badge=...)`
2. Put queries in `selectors.py` and writes in `services.py`, using `core.activity.log_action`.
3. Write thin views in `views.py` with `core.pagination`, `json_ok/json_err` and `csv_response`.
4. In `urls.py`, name routes `admin_coupons_*`; they are auto-included at `admin/coupons/`.
5. Add `templates/admin/coupons/index.html` (extend base, include components; JS in `static/admin_panel/coupons/`).
6. Add `tests/` with an RBAC test and a happy-path test.

The sidebar entry, permission checkbox, middleware enforcement, default redirect and badge all come from the registry, so **no central file needs editing**.

---

## 5. Roadmap (each step ships on its own; URL names unchanged)

**Phase 0 — Hotfix:** ✅ **Done 2026-11-07:** S1, S2, S4, B1, B5, B6, B12, P1, P2. The 267 admin_panel tests and the link-OG tests pass, plus 5 new tests (update_plan rejection, WA resend ×2, WAF regex ×2). **Still open:** B24 (duplicate URL name; you need to decide which toggle to keep).
- S1: `update_plan` accepts only the `PLAN_LABELS` values; dashboard charts use `safe_json`.
- S2: `admin_settings_templates_update` removed from the staff permission map (now super admin only); empty content is rejected.
- S4: `@require_POST` on `admins_destroy`, `qr_files_destroy`, `link_og_delete`, `link_og_toggle`, `toggle_banner_popup`.
- B1: resend works only for a `completed` subscription, sends the stored temp password over WhatsApp and email, and reports the real result. It never calls the activation function.
- B5: paid or Razorpay-paid subscriptions can't be deleted. (Correction: staff were already blocked by the middleware's delete rule; the gap was super admins.)
- B6: promo snapshot uses `discount_type, discount_value, times_used`.
- B12: `total_revenue` = SUM of all completed payments; the trial bar is computed on its own value instead of as the remainder.
- P1: bounded, precompiled `_TEMPLATE_TAG_RE`, and only the first 64 KB of request data is scanned.
- P2: `get_all_feature_flags()` cached for 300 s; `SiteSetting.flush_cache()` clears it.
**Phase 1 — Data safety:** ✅ **Done 2026-11-07** except B10. 308 tests pass (admin_panel, link-OG, agents security) and `manage.py check` is clean. New tests are in `test_audit_phase1.py`, `test_mark_payment_guard.py` and `test_admin_update_plan.py`.
- B2: changing an agent's email in admin is rejected if any other login or agent owns the address; `users`/`auth_user` are synced via `sync_agent_email_change`; both UPDATEs run in `atomic`.
- B3: per-order `cache.add` lock around reconcile execution. Limit: FileBasedCache `add` is not strictly atomic; a Redis or DB unique key would be stronger.
- B4: agent hard-delete aborts if the backup fails and runs in `atomic`. Any real `order_…` id now counts as a payment record, so the agent is soft-deleted.
- B7 (+B25): savepoints around the best-effort calls in insurance approvals and account deletion; approval processing re-checks `is_pending()` under `select_for_update`.
- S3: assigning Starter/Professional/Exclusive via `update_plan` is Super Admin only.
- B11: `mark_payment` → completed now runs `_activate_paid_subscription` (invoice and email still manual). Un-completing sets the subscription to `inactive` and the agent to `pending_payment` when no other paid subscription is active.
- B14: `UTC_TIMESTAMP()` / `datetime.now(timezone.utc)` replaced with IST `now()` in finance, revenue and free_trial.
- B17/B18: manual invoice uses `Decimal`, rejects negative/NaN amounts and base+GST≠total (±₹1), refuses a payment_id that already has an invoice, applies only percentage promos (capped at 100), and on email failure redirects to the list instead of refilling the form.
- B19: distributor `users` + `referral_codes` inserts are atomic.
- S5: changing a user's password or email is Super Admin only; passwords are no longer kept in `form_old`; `hash_password()` is used.
- S7: an admin password reset deletes that admin's other `user_sessions`.
- **Open — B10 needs a business decision:** whether changing a plan should rewrite `selected_plan` on an already-paid row (current behaviour, kept by `test_only_the_current_subscription_changes`) or add a new ₹0 row so revenue-by-plan stays historical.
- **Not in Phase 1, still open:** B8 (reactivation forces `active`), B9 (account deletion falls back to matching by mobile).
**Security follow-up (2026-11-07): S6, S8–S15 done (S13 partly).** 1,183 tests pass.
- S6: per-account lock (10 failures in 15 min → "try again later") on top of the per-IP block. Unknown emails now run a dummy bcrypt check, so response time no longer reveals which admin emails exist. This also fixed a hidden `UnboundLocalError` from local `cache` imports inside `admin_login`. Tests: `AdminLoginAccountLockTests`. MFA is still off (`ADMIN_MFA_ENABLED`): **turning it on in production `.env` is your call.**
- S8: contact-reply email escapes the name, subject and message.
- S9: all 14 `json.dumps|safe` / list `|safe` uses in admin templates now use `safe_json`. This also fixed the free-trial chart, which rendered a Python repr (`None`/`Decimal` broke the JS).
- S10: logout is no longer `csrf_exempt`; the GET link still works.
- S11: run-maintenance-jobs is gated on Super Admin (was `request.user.is_staff`, which was never true), needs POST from the panel, and accepts the cron token from the `X-Cron-Token` header only. `test_prod_readiness_payment_fixes` was updated for this.
- S12: 17 broad `except Exception` handlers no longer send exception text (DB errors, mysqldump stderr) to the browser; they log it with `logger.exception`. ValueError-based validation messages are unchanged.
- S13 (partly): staff with `sessions` can no longer revoke a Super Admin's session. **Not done:** hashing session tokens. It would log out every admin and touches the shared `user_sessions` table that agent and distributor sessions also use, so it needs its own change.
- S14: QR download codes use `secrets.choice`.
- S15: the AMFI social-profile validator checks the real hostname against an allowlist and no longer follows redirects (SSRF).

**Medium/Low bug follow-up (2026-11-07): B13, B15/P5, B16, B20, B21, B22, B23 done.**
- B13: the Renewal Tracker counts only paid and active subscriptions (it used to count checkout attempts, failed and superseded rows). Est. monthly revenue = actual amount paid by current subscribers ÷ 12; it was hard-coded at ₹999/₹499 per agent.
- B15/P5: broadcasts are sent in a background thread (`services/broadcast_service.queue_broadcast`). The `AdminBroadcast` row is created first and its `sent_count` is filled with the real delivered total. Failures are logged. Agent names are escaped in the email HTML.
- B16: one shared `target_agents()` is used by both the email broadcast and the push broadcast pages. Starter = `starter`/`basic`/`standard`; Expiring = trial ending, or a paid subscription expiring, within 30 days.
- B20: renaming a plan no longer changes its slug.
- B21: approve/status change is a conditional `UPDATE … WHERE status = old`. A double click gets a 409, and only one WhatsApp message goes out.
- B22: `parse_int` is used for page numbers. Price, seat and tier forms show "must be whole numbers, nothing saved" instead of a 500. A non-numeric subscription id returns 404.
- B23: `FcmService.send_to_tokens` returns how many pushes FCM accepted. The admin pages report that number and warn when it is 0 (FCM not configured).
- Also: the last two exception-text leaks in `notify.py` were removed (S12).

**Performance follow-up (2026-11-07): P5, P17, P19–P23 done; P3 ready to switch on.**
- P5: broadcasts deliver in the background (see B15).
- P17: new `python manage.py ensure_admin_indexes` checks `information_schema` and reports, or with `--apply` creates, only the missing indexes. It covers agents (status+created_at, pincode, plan_type+trial_ends_at), agent_subscriptions (agent_id+payment_status, payment_status+expires_at), agent_leads (lead_status, created_at), agent_reviews (agent_id+is_approved) and contact_submissions (status+created_at). An existing index with the same leading columns counts as present, so nothing is duplicated. **To do on the server:** run it without `--apply`, review the list, then run it with `--apply`.
- P19: the WAF security alert email is sent from a background thread, not inside the 403 response.
- P20: WAF patterns are compiled once at import.
- P21: for a non-agent Django user who holds an admin cookie, the "is this an agent" lookup is cached for 5 min (it ran on every request).
- P22: the sidebar's Cloudflare-configured flag is cached for 2 min and cleared when credentials are saved.
- P23: the sidebar reads the live `request.admin_user` loaded by the RBAC middleware, so revoked permissions disappear immediately. Admin pages also no longer run 2 session queries for it.
- P3: `settings.py` already switches to Redis when `REDIS_URL` is set and the `redis` package is installed; this is now documented in CLAUDE.md. **Turning it on needs Redis on the host.**
- Noticed, not changed: the WAF alert email falls back to a hard-coded personal Gmail address when `SECURITY_ALERT_EMAIL` is unset (`middleware/security.py`). Set `SECURITY_ALERT_EMAIL` in production `.env`.

**Structure follow-up (2026-11-07): step 7 part 2 finished, step 9 started.**
- Write flows of the remaining **15 modules** moved to `services/<module>_service.py`: agents, delete, finance, subscriptions, users, admins, find_agent_locator, account_deletion, free_trial, quick_registration_leads, coming_soon, calculators, promo_codes, profile_banners, qr_files. That makes **19 view modules** that now call services for their writes.
  - `delete` dispatches through an explicit allowlist (`DELETE_HANDLERS`). The soft-delete rule, mandatory backup and transaction are unchanged.
  - Atomic blocks moved as whole units. Audit logs that need the request are passed in as callbacks.
  - Each module was independently verified: every SQL string is preserved (LOST=0), pyflakes is clean, and the module tests pass. The work was done by 4 parallel agents with disjoint files, then re-checked in this session.
  - Kept in views on purpose: the `toggle_status` conditional UPDATE (a test patches `views.agents.connection`) and `insurance_approvals_approve_onboarding` (tests patch `views.insurance_approvals.ReferralCode`).
- Step 9 (templates):
  - **Shared `{% admin_pagination page %}`** (`apps/admin_panel/templatetags/admin_tags.py` + `templates/admin/components/pagination.html`) replaces the hand-written pagination in **23 templates**. It keeps every current filter URL-encoded (the old links broke on `&`/`#` in a search) and elides long page ranges. Covered by `test_pagination_tag.py`. Skipped on purpose: blacklisted agents (`tab` param), invoices (`folder`), API logs (`service`).
  - `getCookie` defined once in `base.html`; the 2 copies were removed.
  - **Sidebar visibility now comes from the registry:** the context processor builds `nav_open` (the url names this admin may open, via `registry.open_route_names`, which applies the same rule as the RBAC middleware). The 47 hand-written `{% if ... in admin_permissions %}` conditions in `base.html` became `{% if nav_open|any_open:"route,..." %}`; multi-link groups wrap each link separately. Labels, icons, badges and active states are unchanged.
    - Compared old vs new render for super admin, all-staff and each single permission: 16 permission sets differ, and every difference brings the sidebar in line with real access. **Dead links removed** for staff: payment reconcile, WhatsApp, championship and event-referral (super-only); heatmap with `agents`/`geocoding` (needs `pincode`); 4 settings links shown to `logs`/`backups`/`server_health`/`email_templates`/`feature_flags`; analytics/threat logs shown to `error_logs`; the header "View all activity logs" link. **Now shown** where access already existed: Coming Soon (`content`), Profile Banners (`agents`), Card Themes (`site_settings`).
    - `test_sidebar_registry.py` fails if any sidebar link is not openable for the viewing permission.
    - A new module's sidebar link now needs only its route in `registry.ROUTE_PERMISSIONS`; labels and icons are still written in `base.html`.
  - **Still open in step 9:** shared modal partial (23 templates), moving ~13,000 lines of inline JS/CSS to static files, merging the 3 different `showToast` helpers. These change what users see, so they need a browser check against a running server (MySQL), which was not possible here.

**Phase 2 — Safety net:** ✅ **Done 2026-11-07.** 311 tests pass.
- `test_rbac_snapshot.py` + `rbac_snapshot.json`: for all 328 named `/admin` and `/padosi-admin` routes, including championship and event-referral, it records who `AdminPermissionMiddleware` lets through: 4 public (login/logout), 95 super-only, and 229 open to staff holding specific permission keys. **Any** change in access fails the test until the snapshot is regenerated on purpose (`UPDATE_RBAC_SNAPSHOT=1`, see CLAUDE.md §16). It also asserts that no route is unreachable or open to every staff member, and that the key super-only routes stay super-only.
- `apps/admin_panel/conftest.py`: plain `pytest` now stops with the right command instead of 24 `ImproperlyConfigured` errors. pytest-django was not added (it would be a new dependency).
- **Staff lockouts fixed (2026-11-07, on request):** 14 routes that were missing from the middleware map are now open to staff, keyed to the permission whose sidebar section already shows the link:
  - `pincode`: pincode heatmap ×3
  - `content`: invite studio ×2
  - `site_settings`: banner/popup ×4
  - `invoices`: sync a single invoice
  - `blacklisted_agents`: account-deletion requests ×4

  `admin_settings_templates_update` stays super-only on purpose (S2). The snapshot was regenerated and the diff reviewed: only these 14 routes changed.
- The `approvals` key on its own grants nothing; only its children `approvals_awaiting_verification` / `approvals_missing_licenses` open `/admin/approvals/`. This is existing behaviour, now recorded.
**Phase 3 — Performance:** ✅ **Done 2026-11-07 (partly):** 490 tests pass (admin_panel, home, agents security).
- P4: `_get_admin_from_session` is memoised on the request; the middleware, view and context processor share one lookup (was ~7–10 queries per admin page).
- P3 (without Redis): `is_ip_blocked` reads one cached set of blocked IPs (60 s, cleared by a `BlockedIp` save/delete signal) instead of writing a cache file per visitor IP per minute. Only blocked IPs hit the DB.
- P10: dashboard stats cached for 120 s per period. P11: sidebar badge counts cached for 120 s (was 30 s). **Trade-off:** numbers can be up to 2 min old.
- P9/P12: new `streaming_csv_response()` (formula-safe, BOM). All Export Center CSVs and the pincode export stream row by row; the pincode export reads in 2,000-row DB chunks. The agents export joins only the latest subscription, so there is no longer one row per subscription. **Behaviour change:** agents CSV row count = agent count.
- P8: find-agent locator annotates the approved-review average (was 2 queries per agent) and caches pincode coordinates per call.
- P7: the "Missing IRDAI Licenses" list is capped at the newest 200, and the heading shows the real total.
- **Not done:** P6 (pending registrations: SQL UNION + pagination) is a larger rewrite, moved to Phase 4 step 7 with the selector extraction. P3 Redis needs hosting support. P17 indexes need `SHOW INDEX` on the live DB first. P13–P16 and P18 (pincode import, pincode stats, heatmap, geocoding, backup in request) are still open.
**Phase 4 — Structure:** ✅ **Steps 1–4 done 2026-11-07.** Every move was checked against the RBAC snapshot and the test suites.
- Step 1: deleted `models/event.py`, `services/invoice_storage.py` and `services/playwright_manager.py` (no references). A backup copy is in the session scratchpad. Fixed the stale `urls.py` docstring and the CLAUDE.md reference.
- Step 2: new `apps/admin_panel/auth.py` (session cookie, `_get_admin_from_session`, invalidate/clear, `is_super_admin`). `views/dashboard.py` re-exports it for old imports. 17 imports in other apps and the middleware now use `auth`, and 5 test patch targets were updated. `pages._is_super_admin` delegates to it.
- Step 3 (started): both duplicate `_log_activity` raw-SQL helpers delegate to `AdminActivityLog.log()`; the quick-registration CSV uses the shared `streaming_csv_response()`. Remaining `core/` helpers (`paginate`, `json_ok/err`) are to be adopted per module as each one is touched.
- Step 4: `middleware.py` (1,137 lines) → `middleware/` package: `security.py` (WAF, IP helpers, blocking), `ip_whitelist.py`, `session_isolation.py`, `rbac.py` and `exceptions.py`. `__init__.py` re-exports every old name, so `settings.MIDDLEWARE` and the 20+ importers are unchanged. 4 dead duplicate keys in the permission map (`admin_qr_files_*` → "content", always overridden by "qr_generator") were removed; the RBAC snapshot is unchanged.
- Step 5: new **`apps/admin_panel/registry.py`**: `MODULES` (key, label, landing route, sub-permissions) and `ROUTE_PERMISSIONS` (263 url names). The middleware's 300-line dict, its 40-line landing-route map and `admins.get_permissions_list()` all read from it, so `middleware/rbac.py` went from 750 to 227 lines. It was generated from the old code and proven identical: 0 mismatches, RBAC snapshot unchanged. `test_registry.py` checks that every mapped route exists, every permission is declared, and every landing route is open to its own permission. **Adding a module now touches one Python file** (plus urls and views). **Not yet from the registry:** the sidebar in `base.html` (~45 hand-written permission checks); it belongs to step 9 (templates).
- Step 6: `urls.py` (760 lines, 307 routes) → `urls/` package with one file per view module (52 files). `__init__.py` concatenates them. Verified before vs after: `resolve()` of every route and `reverse()` of all 306 names are identical, and an exhaustive check of 1,762 sample paths (including other routes' literal segments as parameter values) shows 0 differences. The RBAC snapshot is unchanged.
- **Adversarial review (workflow, 4 reviewers + 2 skeptics per finding)** of steps 2 and 4–6: no regressions in the middleware split, the urls split or the auth move. One pre-existing bug was confirmed and fixed: a staff member whose first permission was `fastapi_services` landed on the dashboard they cannot open, causing an endless redirect. That module now has no landing route (`registry.landing_route` skips it). This is covered in `test_registry.py`.
- Also fixed: `test_mark_payment_guard` asserted exactly 365 days between two `now()` calls taken milliseconds apart, so it failed intermittently. It now uses a 60 s tolerance.
- **Status:** 1,119 tests pass (admin_panel, home, agents, wa_agent_bot, event_referral, referral_championship, wholesale).
- Step 7 (part 1, 2026-11-07): **read-only raw SQL moved out of 14 view modules into `apps/admin_panel/selectors/<module>.py`** (advanced, agents, dashboard, distributors, events, export, free_trial, invoices, leads, promo_codes, referrals, revenue, search, users; ~90 selector functions). This was done by a workflow: 16 extractors, each editing only its own two files, plus 16 independent equivalence verifiers. Verified separately:
  - every original SQL string still exists (9 copy-pasted duplicates are now one shared selector);
  - pyflakes is clean;
  - 1,178 tests pass (admin_panel, home, agents, distributors, insurance, wa_agent_bot, event_referral, referral_championship, wholesale);
  - the RBAC snapshot is unchanged.

  `sessions` and `account_deletion` had nothing safe to move. Writes, transactional reads and select-for-update stay in the views on purpose.
  - **Decision:** views were **not** physically moved into `modules/<name>/`. 30+ tests patch view-module names and other apps import from `views.*`, so a move would break them for little gain. The layering (views → selectors) is the part that matters.
  - Pre-existing bug found and **fixed**: `free_trial_index` raised `UnboundLocalError` on `settings.DEBUG` when no row had `trial_ends_at` (two function-local `from django.conf import settings` shadowed the module import). The local imports were removed. A regression test in `test_free_trial_test_tool.py` was confirmed to fail on the old code.
- **Performance leftovers done:** P13 (pincode CSV import streams instead of `list()`), P14 (pincode stats/states cached for 10 min, cleared on import/delete), P15 (heatmap bulk-loads coordinates, was 2 queries per cluster), P18 (`mysqldump` 300 s timeout). P16 kept: the geocoding `sleep(1)` is Nominatim's required 1 req/s rate limit.
- Step 7 part 2 (started, 2026-11-07): write flows of **4 modules moved to `services/<module>_service.py`**: insurance_approvals, invoices, distributors, contacts. Verified: every SQL string is preserved, pyflakes is clean, and 343 tests pass. The insurance approvals lock and re-check stay in one transaction. The run for the other 15 modules (agents, delete, find_agent_locator, account_deletion, free_trial, coming_soon, calculators, quick_registration_leads, promo_codes, profile_banners, admins, qr_files, finance, subscriptions, users) **stopped at the subagent usage limit**. Their half-finished edits were rolled back to the backup, so nothing partial is in the code. **To do: re-run after the limit resets.**
- **P6 done:** pending registrations now run a *light* query (no per-row event, blacklist or review subqueries) for every pending agent, which is enough for sorting, stats and pagination. The full query runs only for the 25 agents on the current page (`_build_queue_query(light=True / only_ids=...)`; the default call is unchanged, so the approvals page and its tests are unaffected). Covered by `test_pending_registrations_paging.py`.
- **Step 8 done:**
  - `ReferralCode`, `ReferralUsage`, `AgentServicePincode`, `RegistrationLead` and the Laravel `users` model (now `LaravelUser`) moved from admin_panel to **`apps.agents.models`**. The old import paths still work through re-export modules in `admin_panel/models/`.
  - Migrations `agents 0042` and `admin_panel 0016` are **state-only** (`SeparateDatabaseAndState`, `database_operations=[]`). Rendering them produces **0 SQL statements**, and `makemigrations --check` reports no changes. The signal sender string was updated to `agents.AgentServicePincode`.
  - Note: the `django_content_type` rows for the old `admin_panel.*` models stay until `manage.py remove_stale_contenttypes` is run. They are harmless.
  - Added `AgentStatus` and `PaymentStatus` `TextChoices` in `apps.agents.models`. They are not set as field `choices` (legacy rows may hold other values, and that would also force a migration).
  - All 20 `payment_status` literals in admin_panel Python code were replaced with `PaymentStatus.*` by a tokenizer-based codemod that never touches SQL strings. Agent `status` literals were left as strings because the same values are shared with subscription and lead statuses, so an automatic replacement is not safe.
- **Next:** finish step 7 part 2 (15 modules), then step 9 (templates and sidebar from the registry).

**Phase 4 plan (remaining steps):**
1. Delete dead code (`models/event.py`, `invoice_storage.py`, `playwright_manager.py`).
2. Extract `auth.py` and re-export it from `views/dashboard.py`; repoint the 52 external imports.
3. Add `core/` helpers and adopt them module by module.
4. Split `middleware.py` into a package, keeping re-exports so the settings paths still work.
5. Build `registry.py`; generate the permission map, sidebar and permission list from it; prove in a test that the generated map equals the current dict, then delete the dict.
6. Split `urls.py` per module with `include()`; drop the 265 per-view auth checks (the Phase 2 tests protect this).
7. Move modules into `modules/<name>/`, smallest first; pull raw SQL into `selectors.py`/`services.py`.
8. Fix model ownership (`User`, referrals) and add `TextChoices`.
9. Templates: add `components/` partials and move inline JS/CSS to `static/admin_panel/`.

## Not covered

`apps/referral_championship` and `apps/event_referral` admin views; deep reads of `content.py`, `settings.py` and `invoices.py`; template-side N+1; live MySQL indexes; xhtml2pdf `link_callback` (S2 impact). No tests were executed.
