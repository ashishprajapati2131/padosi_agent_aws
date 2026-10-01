# PadosiAgent: Revenue-Flow Production Audit (registration → referral → payment → approval → subscription)

| | |
|---|---|
| Date | 2026-10-01 |
| Base commit | `main` @ `cefc27a` |
| Working tree | **Not clean.** A different editor made 12 uncommitted changes during the audit (02:59–03:01), plus new migrations `agents/0032` and `event_referral/0002`. They are reviewed in §6 (F-29). |
| Mode | **Report only.** At the owner's request, no application code was changed. The only new files are this report and `docs/audit/poc/poc_audit_20261001.py`, which is not on the test-discovery path. |
| Previous baseline | `docs/audit/AUDIT_BASELINE_2026-09-23.md`. Its fixes were not re-reported unless they have regressed. |
| Method | Four parallel code-path traces (payment/webhook, referrals, admin, subscription/mobile API). I personally re-verified every Critical and High finding in the code, and **reproduced 6 of them with executable tests** (§5). |

> This file describes **open, exploitable** bugs, including one that grants a superuser session. Keep it private.

Evidence levels used below:
- **PROVEN**: a PoC test reproduces the bug against the current tree.
- **VERIFIED**: I read and traced the exact code path.
- **TRACED**: a subagent traced it with file:line evidence, and I did not re-read it line by line.

---

## A. Executive summary

**Overall: NEEDS FIX. Not production-safe for new signups or payments.**

The Sept-23 audit's fixes still hold. Tests went from 306 to 405, all passing, and CI now blocks deploys on test failure. But code added after that audit introduced new critical defects: approval flow `51a9157`, admin reconcile `95bd049`, event referral `09a8699`, and app upgrade handoff `daf439d`/`cefc27a`. A few older defects were also missed.

**Critical blockers**
1. **F-01 (PROVEN): anyone can become a superuser, insurance manager or distributor by paying for a plan with that person's email.** Agent signup never checks whether the email already belongs to a non-agent account. After payment, `create_or_link_django_user()` returns that existing `auth_user` and `login_agent_user()` signs the payer in as them. The PoC logged in as superuser id 1, which opens `/django-admin/`.
2. **F-02 (PROVEN): "payment successful but user not in Pending Approval"; most likely your production bug.** Each click on *Pay* overwrites the pending subscription's `razorpay_order_id`. If the user pays an earlier order (UPI approved late, or the modal was closed and reopened), no path can ever match that payment:
   - the browser callback says "Invalid transaction";
   - the webhook returns **503 forever**;
   - the recovery path and the admin "Verify" button check only the newest order.

   The money is captured and the agent stays `pending_payment`, so they appear in Pending Registrations and never in Approvals.

**Other high-impact problems (details in §C)**
- The webhook path skips championship and event-referral credit (PROVEN).
- The admin reconcile tool can move one agent's payment and invoice onto a new "ghost" agent, invent payment ids, and skip amount checks.
- The FastAPI in-app password change writes a **different person's** `users` row (PROVEN schema mismatch).
- Subscriptions never expire and there is no renewal path.
- The upgrade price charged differs from the price shown, and promo codes crash the upgrade (PROVEN).
- The legacy referral reward ("Pro @ ₹1") is granted at 5 referrals instead of the documented 15, counts ₹0 signups, and repeats at every renewal.
- Staff with `finance_accounts` can mark any unpaid subscription "completed", which unlocks the dashboard.

**Fixes completed in this session: none (report-only by owner decision).** A prioritised, implementation-ready fix plan is in §10.

---

## B. Flow map (as implemented)

| Step | Component / API | DB records | Status transition | Notes / defects |
|---|---|---|---|---|
| Visit / referral link | `/join/<code>/` (`registration.referral_join`), `/agent-registration/join/<code>/`, `?ref=`, `/event-registration/` | session keys `ref_code`, `sub_distributor_id`, `distributor_id`, `championship_ref_id`, `event_referral_registration`; `ReferralCode.clicks += 1` (not atomic) | – | Last link wins; keys survive login except `ref_code` (F-27) |
| Step 1 | `POST /agent-register-step1/` (`register_step1`) | `AgentDraft` (by session/email), existing `Agent` fields overwritten | draft `registration_step=1` | No email OTP (AUD-SEC-018 still open); portal emails not blocked (**F-01**); non-active agents can be overwritten by anyone (F-11) |
| Step 2 | `POST /agent-register-step2/` | `AgentDraft` | step 2 | – |
| Plan | `GET /chooseplan/` | – | – | Price from `SiteSetting.pricing_config` plus promo, social-follow, scratch and championship levers held in the session |
| Checkout | `POST /agent-register/complete/` (`_agent_register_complete_impl`) → `create_agent_from_draft` → `create_checkout_order` | `Agent` (get_or_create by email), `AgentSubscription` (**reused, order id overwritten: F-02**) | Agent → `pending_payment` (**even if already paid or suspended: F-11**); sub `pending/inactive` | ₹0 total → instant completion (skips promo count and hooks) |
| Pay | Razorpay Checkout JS | Razorpay order (`payment_capture: 1`) | – | – |
| Verify | `POST /agent-register/verify-payment/`, `/payment-success/`, `/agent-register/payment-callback/` → `_finalize_razorpay_payment` | sub → `completed/active`, `starts_at=now`, `expires_at=now+365d`; promo `F()+1`; referral hooks; `queue_invoice_and_welcome` (on_commit thread) | Agent → `pending_approval` (or stays `active` for an upgrade) | Signature + amount (±₹1) verified; `select_for_update`; logs payer in (**F-01**) |
| Webhook | `POST /razorpay-webhook/` | same as Verify | same | HMAC verified; **no championship/event hooks, no superseded deactivation (F-05)**; 503 for unknown orders (F-02, F-20) |
| Recovery | `verify_and_activate_pending_payment` (login, dashboard, step 1, chooseplan, failure, admin Verify) | same | same | Checks only the newest pending order; returns True if *any* old payment exists (**F-06**) |
| Admin approval | `/admin/agents/approvals` (`status='pending_approval'`) → `admin_agents_toggle_status` | `agents.status` | `pending_approval → active` (or `suspended` as "reject") | Any status string accepted; no payment check; wrong permission key (F-24) |
| Insurance path | `/insurance/.../record_payment`, online checkout → `/admin/insurance-approvals/` | sub completed, UTR stored in `razorpay_order_id` | Agent → `pending_admin_approval` → `active` | Separate queue (F-15); UTR `order_…` bypasses the gate (F-31) |
| Referral reward | `_credit_referral_conversion` (legacy), `process_championship_qualification`, `qualify_event_referral` | `referral_usages`, `referral_codes.total_referrals`, `championship_*`, `event_referral_*` | usage `converted`; EV row `registered → paid` | Rules differ per system (§E) |
| Dashboard / entitlements | `AgentPaymentGateMiddleware`, `agent_can_access_dashboard`, `feature_unlock` (`agent.plan_type`) | – | – | Any completed payment, ever: **no expiry (F-09)** |
| Upgrade | `POST /agent/upgrade-plan/` (web), app handoff `/agent/app-upgrade/` | new sub row; old subs → `inactive` | plan_type changes | Price mismatch, promo crash, downgrade allowed (F-10); handoff race (F-16) |
| Renewal / expiry | **none** | – | – | No job, no reminder, no renewal checkout (F-09) |
| Refund | webhook `refund.processed` → `_handle_refund_webhook` | sub + invoice `refunded`; agent → `pending_payment` if no other payment | – | Upgrade refund keeps the upgraded plan; legacy referral not reversed (F-22) |
| Cancellation | **none** (no user-initiated cancel) | – | – | Only admin status changes |

---

## C. Issue table

Severity counts: **Critical 2 · High 16 · Medium 14 · Low 10**.

| ID | Module | Issue | Sev | Evidence | Root cause | Fix (planned) | Status |
|---|---|---|---|---|---|---|---|
| **F-01** | Signup / auth | Paying for a plan with a staff, insurance or distributor email logs the payer in **as that account** (superuser included) | **CRITICAL** | **PROVEN** `test_F01…`: session uid == superuser pk. `registration.py` `register_step1` (no check), `_finalize_razorpay_payment` → `create_or_link_django_user` → `login_agent_user`; same at the ₹0 instant-complete path | `find_django_user(email)` returns any `auth_user`; nothing refuses non-agent identities | Reject at step 1 (and events/Paldi/FastAPI) when the email belongs to a non-agent portal user; `login_agent_user` must refuse staff/superuser/insurance/distributor users; `create_or_link_django_user` must not link to them | FIXED `a3d51d2` |
| **F-02** | Checkout / webhook | Retrying checkout orphans a paid order: charged, never activated, missing from Approvals | **CRITICAL** | **PROVEN** `test_F02…`: webhook HTTP 503, agent `pending_payment`. `_agent_register_complete_impl` reuses the pending sub and sets `razorpay_order_id = <new>` | One subscription row per agent, re-pointed at each new order | One pending sub row per order (never overwrite a non-empty order id); webhook falls back to `order.notes` (draft/agent/email already sent); recovery checks **all** open orders; one-off backfill (§10 step 2) | FIXED `3f71a87` |
| F-03 | Events funnel | `/events/register/` POST routes to `show_form`, so `register` and `select_plan` are dead. If ever re-routed, the view overwrites any non-active agent anonymously and `payment_success` logs into any `auth_user` by email | HIGH (latent) | **PROVEN** `test_F13…` (routing). **VERIFIED** `events.py` `register`, `_get_or_create_agent`, `payment_success` → `login(request, user)` | Duplicate URL patterns; no ownership or portal guards | Delete the legacy `/events/` funnel, or apply the F-01 guards before re-routing | FIXED (guards) `577b274`; funnel still unrouted |
| F-04 | Admin reconcile | Reconcile resolves the agent by the **payer's** email, can create a ghost agent, reassigns the real registrant's subscription and invoice, invents `pay_<order>` ids, takes plan from the request and amount from whatever was paid, uses test-mode keys, has no lock, and always demotes to `pending_approval` | HIGH | **VERIFIED** `payment_reconcile.py` execute (~440-620), `_get_razorpay_clients` | Built as "make the record match Razorpay" instead of "activate the order's own subscription" | Key on the order's subscription; refuse if the payment is used elsewhere; `_order_plan_slug` + `_paise_amounts_match`; live keys only; `select_for_update`; keep `active`; shared activation helper; AdminActivityLog | FIXED `dfb6248` |
| F-05 | Webhook | Webhook activation never runs championship/event-referral qualification or `_deactivate_superseded_subscriptions`; when the webhook wins, the callback's `_PaymentAlreadyFinalized` branch skips them too | HIGH | **PROVEN** `test_F05…` (both hooks not called) | Four copy-pasted activation paths have drifted | One `_activate_paid_subscription(sub, payment)` used by callback, webhook, recovery, ₹0, reconcile | FIXED `5fc1451` (webhook), reconcile via `dfb6248`; ₹0 promo signups do not count as paid referrals (by design) |
| F-06 | Recovery | `verify_and_activate_pending_payment` returns True when *any* earlier payment exists, so paid upgrades or renewals whose callback was lost are never recovered; admin Verify says "already active" | HIGH | **VERIFIED** `registration.py` `verify_and_activate_pending_payment` first lines; `admin_panel/views/agents.py` ~1288 | Agent-level check instead of order-level | Check the specific open orders first | FIXED `c76d8f1` |
| F-07 | FastAPI auth | In-app password change sets the password of the `users` row whose **id equals the agent's `auth_user.id`**, i.e. a different person. Insurance `approve_onboarding` has the same id mix-up (`User.objects.get(id=agent.user_id)`) | HIGH | **PROVEN** `test_F07…`: FK `users.id` vs Django `auth_user.id`. `password_reset_service.py` `reset_password` | SQLAlchemy mirror declares the wrong FK target | Resolve the user by email (`user_repo.get_by_email`); fix the mirror FK; same in `insurance_approvals.py` | FIXED `de77f85` |
| F-08 | FastAPI auth | Password reset updates only `users.password`; the old `auth_user` hash still logs in (web accepts either, and API login copies it back) | HIGH | TRACED `password_reset_service.py:186`, `account_auth.verify_agent_password`, `auth_service` sync | Two password stores | Write both hashes (`ensure_django_user`/`ensure_laravel_user`, overwrite) and flush sessions | FIXED `278cbd0` |
| F-09 | Subscription | Expiry never enforced: dashboard gate, entitlements and directory ignore `expires_at`; no job marks expiry; trial never ends; no renewal path (`chooseplan` redirects paid agents; upgrade says "already paid") | HIGH | VERIFIED `account_auth.agent_has_completed_payment`; TRACED feature_unlock, agent_filters, `dashboard.py:2237` | No lifecycle design | Business decision (§4). Then one `active_paid_subscription()` helper + daily expiry/reminder command + renewal checkout | BUILT `75556e4`, admin switch OFF (owner decision) |
| F-10 | Upgrade pricing | (a) Charge applies the ≥20% trial discount to **every** agent, but the display only for trial agents, so a Starter→Pro upgrade shows ₹8,258 and charges ≈₹6,606; (b) any promo code crashes the upgrade (import of a non-existent module); (c) downgrades allowed; (d) parallel pending upgrade orders; (e) mobile API computes a third price from `subscription_plans` | HIGH | **PROVEN** (b) `test_F10…`. **VERIFIED** (a) `dashboard.py` display (~435) vs `agent_upgrade_plan` (~2176) | Three price implementations | One server-side `quote_upgrade()` used by display, charge and API; `upgrade_target_allowed` check; reuse the open order | FIXED `5228a1b` `5383c7b` (owner: charge what is shown) |
| F-11 | Signup | Anonymous step 1 overwrites name/mobile of any agent not `active`/`pending_approval` (suspended, rejected, `pending_admin_approval`…); "Pay" then resets status to `pending_payment` via `create_agent_from_draft`, including agents already paid (webhook-won tab) | HIGH | TRACED `register_step1` reuse branch, `create_agent_from_draft` `agent.status = status` | No state guard; no email ownership (AUD-SEC-018) | Only mutate agents in `incomplete`/`pending_payment`; refuse blocked statuses; email OTP | FIXED `63f7ba5` |
| F-12 | Legacy referral | "Professional @ ₹1" granted at **5** conversions (model tiers say 15); ₹0 and trial signups count; reward never consumed (every renewal ₹1); no self/mobile check; not reversed on refund; FastAPI shows 1/3/5 tiers | HIGH | **VERIFIED** `_credit_referral_conversion` (`>= 5`) vs `ReferralCode.tiers()` (15); TRACED the rest | Three tier definitions | Use `referral_service`; count only real paid, non-trial payments; consume on use; reverse on refund | NOT CHANGED (owner: ignore) |
| F-13 | Admin reconcile UI | Razorpay/DB values inserted with `innerHTML` and inline `onclick` strings (`db.agent.name`, `rz.email`, `rz.contact`, `rz.receipt`) on a superadmin page | HIGH→MEDIUM | **VERIFIED** `templates/admin/payments/reconcile.html:449-526`. Web and dashboard names reject `<>` and the only unvalidated source (the events funnel) is dead, so the current exploit path is unproven | No escaping | `textContent` + `addEventListener` | FIXED `f05a75e` |
| F-14 | Admin finance | `mark_payment` lets `finance_accounts` staff flip any subscription to `completed`; the real `order_` id then unlocks the dashboard; no dates; no `@require_POST`; logged with NULL admin | HIGH | **VERIFIED** `finance.py:332-362` | Manual override without payment proof | Superadmin-only + payment reference required + dates, or remove | FIXED `e81ff85` |
| F-15 | Insurance approvals | `approve_onboarding` has no status check (any agent id → `active`), picks an unordered `.first()` sub, re-POST creates duplicate invoice and email, no log; reject marks a *paid* subscription `failed`; insurance-paid agents (`pending_admin_approval`) are invisible to the main Approvals queue and badge | HIGH | **VERIFIED** `insurance_approvals.py:117-150`; TRACED queues | No state machine | Require `pending_admin_approval` under lock; idempotent; show in the main queue; model refunds | FIXED `a54f30e` |
| F-16 | App upgrade handoff | Token marked used **after** login and the return value is ignored, so concurrent POSTs both get sessions; any current session (distributor/insurance/staff/other agent) is silently logged out and replaced (login-CSRF); grants a full session | HIGH | **VERIFIED** `auth.py` `app_upgrade_handoff` (~354-398) | "burn after login" change in `cefc27a` | Conditional UPDATE first, bail if 0 rows; "continue as X?" interstitial when another user is signed in | FIXED `c126280` |
| F-17 | Event referral | (a) Fraud-rejected (self/same-mobile) referrals are flipped to `PAID, counts=True` on payment; (b) admin *extend* and *restore* always 500 (view name shadows the service); (c) `_grant_win` overwrites a paid plan and creates no subscription; (d) the Paldi session flag is sticky on shared stall devices | HIGH | **VERIFIED** (a) `qualification_service.py` `_fraud_reject` + `qualify_event_referral`; (b) `admin_views.py:13,108,151`. TRACED (c)(d) | Missing state guards | Return on REJECTED; alias the import; skip paid/won agents; pop the flag | FIXED (a)(b) `284dcc6`, (c) `03bc6b8`, (d) `f352f0d` |
| F-18 | Championship | Claims can be re-submitted after dispatch (status overwritten); `is_fraud_blocked` / `is_unlocked` not enforced server-side (web + API) | HIGH | TRACED `agent_dashboard.py:705-717`, `fastapi_app/routers/championship.py:415-434` | UI-only checks | Only unlocked→processing under lock; refuse blocked | FIXED `f9d63a1` |
| F-19 | Payment | `authorized` is treated as paid (webhook `payment.authorized`, recovery, reconcile) | MEDIUM | VERIFIED webhook event list | – | Activate on `captured`/`order.paid` only | FIXED `b6966d9` |
| F-20 | Webhook | 503 for every order without a subscription (insurance single checkout never stores its order id), so Razorpay retries indefinitely and may disable the webhook | MEDIUM | VERIFIED webhook; TRACED `insurance/views/payments.py:237` | – | 200 for orders not tagged as registration orders | FIXED `a6b6fb6` |
| F-21 | Fulfilment | Invoice and welcome email run once in an in-process thread; nothing retries after a crash or worker recycle; invoice dedupe only by payment id | MEDIUM | TRACED `post_payment.py`, `invoice.py:172` | Cron reverted in `236fd60` | `fulfilled_at` flag + idempotent retry command | FIXED `eb2eaca` + cron `b8333a3` |
| F-22 | Refund | Refunding an upgrade keeps the upgraded `plan_type` (the previous sub was deactivated); legacy referral not reversed; championship claims not cancelled | MEDIUM | TRACED `_handle_refund_webhook` | – | Reactivate the previous sub; reverse all referral systems | FIXED `4228962` |
| F-23 | Admin audit | `AdminActivityLog.log` reads `session['admin_id']`, which admin login never sets, so every log has a NULL admin; reconcile, verify, toggle_status, update_plan, insurance approve/reject, promo CRUD, manual invoices and exports are not logged at all | MEDIUM | **VERIFIED** `admin_activity_log.py:30` vs `dashboard.py:327` (stored in `user_session_data`) | – | Pass `admin_id` explicitly; log all money/approval actions | FIXED `ce93308` |
| F-24 | Admin approvals | `toggle_status`/bulk accept any status string, approve without a payment check, "Reject" = `suspended` with the paid sub untouched; approve buttons require the `agents` permission, not `approvals` | MEDIUM | TRACED `agents.py:233-339`, `approvals.html:567,595` | – | Status whitelist + transition table | FIXED `84f4fb0` |
| F-25 | Admin plans | `update_plan` rewrites `selected_plan` on **all** historic subscription rows and grants plan features with no payment or log | MEDIUM | TRACED `agents.py:594-657` | – | New sub row with reason; log | FIXED `93cf1f3` |
| F-26 | Admin free trial | `ft_force_test_credit` inserts fake active agents and applies referral rewards in production | MEDIUM | TRACED `free_trial.py:428-504` | Test tool left in prod | DEBUG + superadmin only, or remove | FIXED `3dee579` (DEBUG only) |
| F-27 | Attribution | Referrer is last-touch and can be overwritten (step 1, `create_agent_from_draft`, checkout); session distributor keys beat `ref_code`; keys survive login; EV OneToOne IntegrityError swallowed, so nobody is credited | MEDIUM | TRACED `_assign_step1_draft_fields`, `create_agent_from_draft` | – | First-touch once set; clear all keys together | NOT CHANGED (owner: ignore) |
| F-28 | Exports | CSV and Google-Sheet cells not neutralised (`= + - @`), so formula injection is possible via agent names | MEDIUM | TRACED `export.py:29-45` | – | Prefix `'` | FIXED `3a30763` |
| F-29 | Uncommitted changes | New step-1 rate limit keys on `X-Forwarded-For[0]` (violates CLAUDE.md invariant #4: spoofable, and lets an attacker lock out a chosen IP); bcrypt cost lowered 12→10; Redis `OPTIONS={'IGNORE_EXCEPTIONS': True}` is a django-redis option (Django's built-in `RedisCache` passes it to the connection pool, which is SUSPECTED to fail if `REDIS_URL` is set) | MEDIUM | **VERIFIED** `git diff` | – | Use `ThreatMonitorMiddleware.get_client_ip()`; decide on bcrypt cost; test Redis before enabling | FIXED `0af91dc` (bcrypt cost stays 10) |
| F-30 | FastAPI auth | No per-account login throttle (per-IP, per-process only) | MEDIUM | TRACED `auth_service.py:13` | – | Reuse web email throttle | FIXED `48f3a8e` |
| F-31 | Insurance offline | UTR stored in `razorpay_order_id`: a UTR typed as `order_…` passes the real-payment gate; free-text payment date sets expiry | MEDIUM | TRACED `insurance/views/payments.py:98` | Field reuse | `payment_source`/`offline_reference` fields | FIXED `3a65c73` |
| F-32 | Admin invoices | Manual "paid" invoices for any email (blocks that person's signup); sheet URL any https host, then all invoices' PII + PDFs are POSTed to it | MEDIUM | TRACED `invoices.py:254-542` | – | Allow-list `script.google.com`, superadmin-only, log | FIXED `13861df` |
| F-33 | Time | FastAPI compares IST-naive DB values with `utcnow()` (5h30m skew on active/trial checks); admin stats use `UTC_TIMESTAMP()` | LOW | TRACED `dashboard_service.py:60,222`, `plan_service.py:181` | – | `datetime.now()` | FIXED `5fef83c` |
| F-34 | Money | Float pricing; invoice recomputes base as `total/1.18`; upgrade GST rounded differently | LOW | TRACED | – | One `Decimal` pricing function; store base/GST on the sub | KEPT (display = charge; ±₹1 rounding by design) |
| F-35 | Promo | ₹0 paths never increment `times_used`; invalid codes saved on the sub; `max_uses` race; promo trial length ignored | LOW | TRACED | – | Increment in the shared activation helper | FIXED `89a50cb` |
| F-36 | DB | No index on `agent_subscriptions.razorpay_order_id`/`razorpay_payment_id` (every callback/webhook filters on them); `Invoice.razorpay_payment_id` not unique; `ReferralCode.agent` not unique; no unique on `ChampionshipReferral(campaign, referred_agent)` | LOW | VERIFIED `models.py:657-670` | – | Additive indexes (non-unique, to keep the insurance bulk cart working) | FIXED `ab6c646` (migration 0033) |
| F-37 | Admin perf | `agent_list` loads all agents with 3 correlated subqueries and paginates in Python; approvals / pending / subscriptions unpaginated; exports unbounded; insurance approvals 4 queries per agent | LOW | TRACED | – | SQL LIMIT, `select_related`, streaming CSV | PARTLY FIXED `c81dfe0` (agent list); other lists unchanged |
| F-38 | Counters | `ReferralCode.clicks`/`SubDistributor.clicks` read-modify-write (full-row save can clobber `total_referrals`); championship count not locked | LOW | TRACED | – | `F()` updates; lock the participant | FIXED `094925e` |
| F-39 | Jobs | `process_event_referral_expirations` is never scheduled; there is no scheduler at all | LOW | TRACED | – | cPanel cron (see §10) | FIXED `b8333a3` (docs/CRON_JOBS.md; cron still to be added in cPanel) |
| F-40 | Dead code | `admin_panel/views/agent_referral.py`, `fastapi_app/services/payment_verification.py`, legacy `/events/` views; revenue report counts `basic` but activation writes `starter` | LOW | TRACED | – | Remove / fix label | FIXED `7315bc5` `b44356e`; legacy /events/ views kept (guarded) |
| F-41 | Admin delete | Hard delete with `FOREIGN_KEY_CHECKS=0` orphans subscriptions and invoices | LOW | TRACED `delete.py:78-83` | – | Soft-delete | FIXED `6bdb121` |
| F-42 | Mobile API | Forgot-password reveals whether an account exists; `BLOCKED_AGENT_STATUSES` lacks `deleted` | LOW | TRACED | – | Generic message | FIXED (`deleted`) `6bdb121`; message kept (owner commit f4238cc) |

---

## D. Registration report

| Case | Result | Evidence |
|---|---|---|
| Valid registration → Razorpay → dashboard | PASS | existing `test_registration_e2e.py` (green) |
| Duplicate email creates a second agent | PASS (prevented) | `Agent.email` unique |
| Double-submit of *complete* | **FAIL**: concurrent requests can each create a pending sub; every retry overwrites the order id (**F-02**) | PROVEN F-02 |
| Staff / insurance / distributor email | **FAIL (CRITICAL)** | PROVEN F-01 |
| Existing suspended / rejected agent email | **FAIL**: fields overwritten anonymously, status reset on Pay | F-11 |
| Email verification / OTP | **NOT PRESENT** (AUD-SEC-018, still open) | `draft.email_verified = True` set unconditionally |
| Name with `<>` | PASS on web and dashboard (rejected); FAIL on legacy events (dead) | VERIFIED |
| Photo upload type | PASS (bytes-sniffed; prior fix) | baseline |
| Rate limiting | PARTIAL: uncommitted per-IP limit uses a spoofable IP (F-29) | VERIFIED |
| Partial registration leaves broken rows | PASS WITH WARNINGS: drafts accumulate (no unique email); agents created at checkout | TRACED |

## E. Referral report

**Attribution rule per system** (the owner should confirm which is intended):

| System | Captured from | Counts when | Paths that credit | Anti-abuse | Refund |
|---|---|---|---|---|---|
| Legacy `ReferralCode` | `/join/<code>/`, `?ref=` → session → `agent.referred_by_code` (last write wins) | Any completed sub, **including ₹0 and trial**; 5 conversions → Pro @ ₹1 | callback, verify, webhook, ₹0 | none (no self/mobile/IP check, `is_active` not checked) | **not reversed** |
| Championship `PA-` | session `championship_ref_id` (discount) + `referred_by_code` (credit) | completed payment within the campaign | **callback and verify only** (not webhook, F-05) | `is_fraud_blocked` only filters the leaderboard | count reverted; claims kept |
| Event `EV-` (Paldi) | session `ref_code` → `referred_by_code`; row at agent creation | real Razorpay payment before the referrer's deadline | **callback and verify only** | self, same-email and same-mobile rejected, **but undone on payment (F-17a)** | count reverted unless already won |
| Sub-distributor | `/join/<code>/` → session (sticky) | no reward logic | step 1 + checkout | – | n/a |

**Referral becomes official:** at *payment completion* for all three reward systems. None waits for admin approval, so a payment later rejected by an admin still counts.

**Duplicate-reward protection:** EV and championship are idempotent per referred agent. The legacy system recomputes `total_referrals` from usages, which is idempotent for counting, but the reward is a flag that is never consumed (F-12).

## F. Plan & payment report

| Check | Result |
|---|---|
| Server-side price (web registration) | PASS: from `pricing_config` + session levers; the order amount is created server-side; paid amount checked ±₹1 on callback, webhook and recovery |
| Server-side price (upgrade) | **FAIL**: charged ≠ displayed (F-10a); promo crash (F-10b) |
| Server-side price (mobile) | WARNING: display-only, different source (F-10e); FastAPI creates no orders |
| Signature verification | PASS (callback HMAC, webhook HMAC). The DEBUG-only `test_signature_skip_verification` bypass is gated on `settings.DEBUG` |
| Webhook idempotency | PASS for duplicates (row lock + completed check); **FAIL** for side effects (F-05) and orphaned orders (F-02) |
| Out-of-order events | PASS: `payment.failed` is ignored after capture; `payment_failure` never touches completed subs |
| Browser closed after pay | PARTIAL: webhook activates, but no championship/event credit (F-05); fulfilment not retried (F-21) |
| Refund | PARTIAL (F-22) |
| Cancellation | NOT IMPLEMENTED |

## G. Subscription report

- **Activation:** `starts_at = now`, `expires_at = now + 365d` (trial: SiteSetting days) on every path; `SubscriptionPlan` has no duration field.
- **Expiry: not enforced anywhere that matters** (F-09): the gate accepts any completed payment ever; entitlements come from the `agent.plan_type` string; directory listing uses `agent.status='active'`.
- **Renewal:** no path (F-09). **Upgrade:** full price, no proration, old time lost, downgrade allowed (F-10). **Cancellation:** none.
- **State map (actual):**
  - Agent: `incomplete → pending_payment → pending_approval → active`. Also `pending_admin_approval` (insurance) and `event_challenge` (Paldi).
  - Admin can set any string (F-24).
  - Payment can move `suspended/rejected/blacklisted → pending_approval` (F-11/F-05 transition bug).
  - Subscription: `pending/inactive → completed/active → inactive (superseded) | refunded`. `expired` is never written.

## H. Security report

| Vulnerability | Sev | Component | Fix | Verified |
|---|---|---|---|---|
| Account takeover of staff/insurance/distributor via paid signup | CRITICAL | registration | F-01 plan | PoC FAIL (vulnerable) |
| Wrong-user password write (mobile) | HIGH | FastAPI | F-07 plan | PoC FAIL (vulnerable) |
| Old password survives reset | HIGH | FastAPI | F-08 plan | traced |
| Handoff token replay + session swap | HIGH | web auth | F-16 plan | code-verified |
| Staff can activate unpaid agents (`mark_payment`, `toggle_status`, insurance approve, `update_plan`, `force_test_credit`) | HIGH/MED | admin | F-14/15/24/25/26 | code-verified / traced |
| DOM XSS on reconcile page | MEDIUM | admin template | F-13 | code-verified, exploit path unproven |
| Unauthenticated tampering of non-active agents | HIGH | step 1 | F-11 + OTP | traced |
| CSV/Sheets formula injection | MEDIUM | exports | F-28 | traced |
| Spoofable IP in new rate limit | MEDIUM | uncommitted | F-29 | code-verified |

Still-open items from the baseline: AUD-SEC-018 (no email OTP), AUD-SEC-019 (PAN data in git), fake reviews. **Not re-checked this pass:** CORS, file uploads, CSP. Those were covered in the baseline and the relevant code is unchanged.

## I. Performance report

No load test or production measurement was possible, so no numbers are claimed. Structural issues:
- missing indexes on Razorpay id columns (F-36);
- Python-side pagination and unbounded admin lists/exports (F-37);
- 4 queries per row on insurance approvals;
- reconcile doing PDF + email + Google HTTP inside a DB transaction (holds row locks during network I/O).

The uncommitted index migration `0032` (agents.status/mobile/referred_by_code/event_id, draft.email) is additive and safe for MySQL online DDL.

## J. Production readiness checklist

| Area | Status | Evidence |
|---|---|---|
| Registration | ❌ FAIL | F-01, F-11 |
| Authentication | ❌ FAIL | F-01, F-07, F-08, F-16 |
| Referral | ⚠️ WARNING | F-12, F-17, F-27 |
| Plans / pricing | ⚠️ WARNING | F-10 |
| Payment | ❌ FAIL | F-02 |
| Webhooks | ⚠️ WARNING | F-05, F-20 |
| Approval | ⚠️ WARNING | F-15, F-24 |
| Subscription lifecycle | ❌ FAIL | F-09 |
| Tracking / attribution | ⚠️ WARNING | F-27; tracking is session-only (does not survive a device change) |
| Rewards | ⚠️ WARNING | F-12, F-18 |
| Admin | ⚠️ WARNING | F-04, F-14, F-23 |
| Notifications | ⚠️ WARNING | email failure never breaks payment (PASS); no retry (F-21); no renewal/expiry emails |
| Security | ❌ FAIL | F-01 |
| Database | ⚠️ WARNING | F-36, F-41 |
| Performance | ⚠️ WARNING | F-37 (unmeasured) |
| Deployment | ✅ PASS | CI runs the full suite as a blocking gate; `check` passes; SECRET_KEY fail-closed; HSTS/secure cookies |
| Backups | ⚠️ WARNING | pre-migration `backup_database` exists but failure only warns ("continuing carefully") |
| Monitoring | ⚠️ WARNING | Sentry optional (unset locally); `verify_production_env` exists |

---

## 1. WHAT I AUDITED
- Agent web registration (step 1/2, chooseplan, complete, verify, callback, success, failure, webhook, refund).
- `account_auth`, the payment gate middleware, `post_payment`, and invoice creation.
- Legacy `/events/` funnel, Paldi `event_referral` app, `referral_championship`, legacy `ReferralCode`/`ReferralUsage`, sub-distributor attribution.
- FastAPI referral / plans / auth / password reset.
- Admin: reconcile, approvals, pending registrations, `toggle_status`/bulk, `update_plan`, `mark_payment`, free trial, promo codes, plans, invoices, exports, delete, insurance approvals, audit logging, permission middleware.
- Insurance offline and online payments.
- Subscription lifecycle and entitlements.
- App→web upgrade handoff.
- Settings, CI workflow, deploy and rollback scripts.
- The uncommitted working-tree changes.

## 2. WHAT WAS BROKEN
All 42 items in §C. The two that must be fixed before taking more payments: **F-01** and **F-02**.

## 3. WHAT I FIXED
**Nothing.** The owner chose report-only mid-audit after an unknown editor changed files concurrently. The fix plan is in §10.

## 4. WHAT I COULD NOT VERIFY
- Live Razorpay: webhook delivery, retry and disable behaviour, `authorized` vs `captured` timing, test vs live keys on the server. The gateway was mocked.
- Production data: how many orphaned paid orders (F-02) exist today, whether `users.id` and `auth_user.id` collide (F-07 blast radius), the real `admin_activity_log` columns (F-23 schema doubt), and `referral_usages` DB constraints.
- MySQL-specific behaviour (tests run on SQLite), the proxy chain / real client IP, Redis.
- Browser / UI behaviour (double-click, back button, mobile): not run.
- **Business rules needing owner decisions:** intended upgrade discount (F-10a), referral tiers (F-12), first- vs last-touch attribution (F-27), expiry/renewal policy and grace period (F-09), and whether admin approval should gate referral credit.

## 5. TEST RESULTS
| Run | Result |
|---|---|
| Baseline full suite `manage.py test apps fastapi_app` (tree as found, before the concurrent edits) | **405 run, OK** |
| Full suite on the current tree (with the other editor's uncommitted edits, ~03:15) | **409 run: 1 FAIL, 4 ERROR.** The failure `event_referral.tests.test_step1_finalize_creates_challenge_agent` (step 1 now returns 400) passed in the baseline, so it is a **regression introduced by the uncommitted edits**. The 4 errors are in the other editor's new `apps/agents/test_registration_benchmark.py` (its fixture violates `pincodes.latitude NOT NULL`). **Do not commit those edits until this is green.** |
| `makemigrations --check` on the current tree | No changes (the uncommitted `0032` absorbs the old drift) |
| PoC suite `docs/audit/poc/poc_audit_20261001.py` (asserts correct behaviour) | **6 run, 6 FAIL**, meaning all 6 bugs reproduce: F-01, F-02, F-05, F-07, F-10(b), F-03 routing |

Run the PoC suite:
```bash
PYTHONPATH=docs/audit/poc DEBUG=True python manage.py test poc_audit_20261001 --noinput
```
Once fixed, move each test into `apps/agents/test_audit_security.py`; they should then pass.

## 6. SECURITY FINDINGS
See §H. Open: 1 Critical, 6 High (security), plus the baseline's open items.

## 7. DATABASE FINDINGS
- Unindexed Razorpay id lookups (F-36).
- No uniqueness on invoice payment id, `ReferralCode.agent` or `ChampionshipReferral`.
- Mirror FK mismatch `agents.user_id` (F-07); SQLAlchemy writes UTC timestamps into IST tables.
- `upgrade_discount_percent` is an int in Django but Numeric in SQLAlchemy.
- Hard delete with FK checks off (F-41).
- History rewrites via `update_plan` (F-25).
- Pending migration drift was fixed by the uncommitted `0032`.

## 8. PERFORMANCE FINDINGS
See §I.

## 9. PRODUCTION READINESS
| Category | Status |
|---|---|
| Registration | **NEEDS FIX** (F-01, F-11) |
| Payment / webhook | **NEEDS FIX** (F-02, F-05, F-06) |
| Referral / rewards | **NEEDS FIX** (F-12, F-17) |
| Approval / admin | **NEEDS FIX** (F-04, F-14, F-15) |
| Subscription lifecycle | **BLOCKED** on an owner decision (F-09) |
| Mobile API auth | **NEEDS FIX** (F-07, F-08) |
| Deployment / CI | PASS WITH WARNINGS |
| Overall | **NEEDS FIX** |

## 10. REMAINING ACTION ITEMS (fix plan, in order)
Every step is small, preserves existing data, and gets a regression test (the PoC tests become those tests).

1. **F-01 takeover (hours, today).**
   - Add `_email_owned_by_non_agent_account(email)`: an `auth_user` that is staff/superuser/insurance/distributor, or a `users` row with a non-agent role, and not already linked to an Agent. Refuse in `register_step1`, Paldi finalize and the events funnel.
   - `login_agent_user()` refuses to log in such users; `create_or_link_django_user()` refuses to link them.
   - Then check production for agents whose `user_id` points at a staff/insurance/distributor user.
2. **F-02 orphaned payments.**
   - Never overwrite a non-empty `razorpay_order_id`; create a new pending sub per order.
   - Webhook fallback via `order.notes` (draft/agent).
   - Recovery checks all open orders.
   - **Backfill:** a management command that lists Razorpay captured payments for the last N days (`client.payment.all`) and reports/activates any whose order has no completed sub. Dry-run first, then admin-approved. This recovers already-affected customers.
3. **F-05/F-06/F-19** one shared `_activate_paid_subscription()` used by every path: captured-only, all side effects, superseded handling, a single status transition table (never un-suspend; keep `active`).
4. **F-07/F-08** mobile password write by email to both stores; fix the mirror FK; fix insurance approve.
5. **F-16** burn the handoff token before login; interstitial for other signed-in users.
6. **F-04/F-13/F-14/F-15/F-23/F-24** admin: rebuild reconcile on the shared helper keyed on the order, escape the template, restrict `mark_payment`, state-check approvals, fix `admin_id` logging.
7. **F-10b** promo import fix (1 line); F-10a/F-12/F-27/F-09 after the owner's business decisions.
8. **F-17/F-18** event referral and championship state guards.
9. **F-29** before committing the other editor's work: switch the rate limit to `ThreatMonitorMiddleware.get_client_ip()`, decide on the bcrypt cost, and don't enable Redis until tested.
10. **F-36** additive indexes on `agent_subscriptions(razorpay_order_id)` and `(razorpay_payment_id)`.
11. **Scheduler:** a cPanel cron for event expirations, fulfilment retry and (after F-09) expiry/reminders.
12. AUD-SEC-018: email OTP at step 1. It closes F-11 and most attribution tampering.

## 11. Fix log

### 2026-10-01: F-01 and F-02 fixed (branch `fix/f01-f02-signup-takeover-orphaned-orders`, not merged)

**F-01: portal-account takeover via paid signup**
- `account_auth.py`: added `is_non_agent_portal_user()` (staff, superuser, insurance profile, distributor group) and `email_owned_by_non_agent_account()` (those users, or a `users` row whose role is not agent, client or user).
- `create_or_link_django_user()` no longer rewrites a distributor or insurance `users.role` to `agent`.
- `register_step1` returns 422 for such emails ("use a different email"). This is the primary fix.
- `login_agent_user()` (every payment auto-login) refuses those users. This covers agent rows created before the fix.
- The events `payment_success` now uses `login_agent_user()`.
- The app upgrade handoff refuses them and sends them to the normal login.

**F-02: orphaned paid orders**
- `_agent_register_complete_impl` creates one `AgentSubscription` row per Razorpay order. It only reuses a pending row that has no order yet; the web upgrade already worked this way.
- `verify_and_activate_pending_payment` checks the agent's 5 newest open real orders, not only the newest.
- New `adopt_orphan_registration_order()` rebuilds the lost row of a paid registration order. It requires receipt `agent_draft_*` and uses the server-written order notes for email and plan, the order amount, and a check that the notes email matches the draft. It is called from the webhook and the browser callback before they give up.
- New command `recover_orphaned_payments [--days N] [--apply]` lists captured registration payments that never activated. With `--apply` it rebuilds the row and runs the normal recovery: amount re-check, invoice and welcome email. Agents who already have another completed payment are reported as possible double charges and are **not** activated.

**Tests**
- New `apps/agents/test_signup_takeover_orphan_orders.py` (16 tests). Against the old code 14 fail; the 2 that pass guard non-regression (guest-client email can register; a normal payer is still auto-logged-in).
- Full suite: 425 run, 1 failure, the other editor's timing benchmark `test_batch_registration_percentiles` (p50 328 ms vs 150 ms target). It failed identically on HEAD `0e370ea` before these changes. **It will block CI deploys.**

**No-regression review (same day)**
- Portal `users` roles are now an explicit deny-list (`distributor`, `insurance`, `admin`). Any other role, including unexpected legacy values, behaves exactly as before: the user can register and the role becomes `agent` (FastAPI login needs `agent`).
- Checked that sound agents are unaffected: the app never grants `is_staff`/superuser or the distributor group to agents; `role='insurance'` is only used for insurance-company users.
- Admin Approvals / Pending Registrations show the agent's latest completed subscription, falling back to the latest one. Previously a paid earlier order could look "pending". Agents with a single row display exactly as before.
- Every other subscription lookup was checked: payment flows key on the order id, and FastAPI reads only `status='active'` rows.
- Recovery checks the newest order first. Agents with one open order make exactly one Razorpay call, as before.
- No schema change and no migration. `check`, `check --deploy` and `makemigrations --check` are clean.
- Full suite: **427 run, all OK**. `test_batch_registration_percentiles` is timing-dependent: it passed in the 44 s run and failed in the 170 s run.
- Not run: a real browser and live Razorpay test mode. There is no local MySQL/`.env`, so the app can't start here. The Django test client exercises the real views end-to-end with the gateway mocked.

### 2026-10-01: referral fixes (same branch, uncommitted)
- **F-05:** the webhook now runs the championship and event-referral qualification hooks and `_deactivate_superseded_subscriptions`, in the same order as the browser callback. Both hooks are idempotent (counts are recomputed from referral rows).
- **F-17a:** `qualify_event_referral` returns early for a `REJECTED` row (self / same email / same mobile), so paying no longer makes it count.
- **F-17b:** the event-referral admin views import the service as `restore_participant_service`, so Extend and Restore work. `admin_restore_participant` on a WON participant only extends the deadline; status and agent are unchanged.
- **F-18:** reward claim, on the web (`claim_reward_ajax`) and the API (`/claim-reward`):
  - refuses fraud-blocked participants (403);
  - refuses inactive, Top-3 or non-claimable slabs (400), using the same reward types as the Claim button;
  - locks the claim row and allows submit/update only while it is `locked`/`unlocked`/`processing`; otherwise 409.
  - Address updates before the team acts still work.
- Tests: `apps/referral_championship/test_referral_fixes_20261001.py` (13). Against the old code 11 fail; the 2 that pass guard non-regression. Full suite: **440 run, all OK**. No migration.


### 2026-10-01: all remaining findings (same branch, one commit per fix, not pushed)
- Every finding in §C now has its commit id in the Status column. Each fix is its own commit, so `git revert <id>` undoes exactly that fix. Commits that add a migration: `ab6c646` (0033, additive indexes only).
- Every code fix has its own test file, run against the old code first: it fails there, except the non-regression cases. The doc-only and dead-code commits have no test. Full suite after the last commit: **557 run, all OK**.
- Not changed by owner decision: F-12 (tiers), F-27 (attribution), F-34 (floats; display equals charge), the F-42 forgot-password message, bcrypt cost 10, manual admin activation.
- Expiry (F-09) is built but **OFF** until switched on in Admin → Settings → Security.
- F-37 is partial: only the agent list was paginated in SQL. Approvals, pending and subscription lists are unchanged (UI change; needs browser testing).
- After deploy: see `docs/CRON_JOBS.md` (one-time recovery dry runs, then the cron jobs).
- Still not run: a real browser and Razorpay test mode against MySQL.

### Owner decisions
- **2026-10-01:** a referral counts at **payment completion**, not at admin approval. This is the current behaviour of all three reward systems; keep it.
- **2026-10-01:** F-10a: charge exactly the price shown; the upgrade discount applies to trial agents only.
- **2026-10-01:** F-09: build subscription expiry behind an admin switch, default OFF.
- **2026-10-01:** F-26: the fake-conversion test tool works only with DEBUG.
- **2026-10-01:** F-29: keep bcrypt cost at 10.
- **2026-10-01:** F-12, F-27 and referral reversal policy: leave as is.
- **2026-10-01:** F-42: keep the "account not found" message (owner commit f4238cc).
