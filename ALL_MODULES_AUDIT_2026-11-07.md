# All-Modules Audit (excluding admin panel): 2026-11-07

**Scope**

| Area | Python lines | Templates |
|---|---|---|
| `apps/agents` | 29.4K | `templates/agents` (26.5K lines) |
| `fastapi_app` | 13.4K | |
| `apps/home` + `padosi_agent/` (settings, routing) | 11.4K | public templates |
| `apps/wa_agent_bot` + `apps/chatbot` | 8.3K | |
| `apps/wholesale` + `apps/insurance` + `apps/distributors` | 6.7K | |
| `apps/referral_championship` + `apps/event_referral` | 5.7K | |

The admin panel has its own report, `ADMIN_PANEL_AUDIT_2026-11-07.md`.

**Method**
- Seven parallel read-only audits, one per area, each checking security, bugs, performance and structure.
- I re-checked the top finding of every area by reading the code. Those are marked ✅. Anything an auditor could not confirm is marked UNVERIFIED.
- No code was changed and no tests were run.

## Headline numbers

| Module | Critical | High | Medium | Low |
|---|---|---|---|---|
| WhatsApp bot + chatbot (WA) | 1 | 4 | 9 | 3 |
| Agents: registration / payment / auth (PAY) | – | 4 | 7 | 5 |
| Agents: dashboard / profile / public (AG) | – | 3 | 9 | 8 |
| FastAPI (API) | – | 3 | 10 | 7 |
| Public site + config (WEB) | – | 4 | 9 | 3 |
| Insurance / distributors / wholesale (INS) | – | 2 | 10 | 7 |
| Championship + Paldi event (CH) | – | 3 | 8 | 7 |
| **Total** | **1** | **23** | **62** | **40** |

### Fix first (this week)

These are account takeovers, money leaks, or things already broken in production.

1. **WA1 ✅ (Critical):** the WhatsApp bot can reset the password of *any* existing login (staff, insurance, distributor) by email, then send the new password to the attacker.
2. **PAY1 / PAY2 / PAY3 ✅:**
   - PAY1: anyone can take over an unpaid agent's registration with only their email.
   - PAY2: a Razorpay signature works as a permanent, reusable login link.
   - PAY3: replaying an old payment link drops the agent to the old plan.
3. **PAY4 ✅:** starting a new renewal deletes the previous renewal's Razorpay order. If that order is paid late, the money is taken and the agent is never activated.
4. **WEB1 ✅ / AG1 ✅:** stored XSS on `/find-agents/` (company names typed by agents) and on public profiles (the Google Business URL accepts `javascript:`).
5. **WEB2 ✅:** exit-popup leads and Google-review clicks return 404 in production, because these Django `/api/*` routes are sent to FastAPI.
6. **CH1 ✅ / CH2 ✅:**
   - CH1: setting the championship to "ended" crashes every campaign page.
   - CH2: the 50% campaign price still applies although the campaign ended on 2026-10-31.
7. **API1 ✅:** the FastAPI account-deletion status endpoint has no authentication, accepts guessable reference IDs, and returns the email, mobile and name.
8. **INS2 ✅:** the insurance *sales* role can record payments and send agents for activation.

## Phase 7 status (2026-11-14) — FastAPI (API5–API20)

Tests: `fastapi_app/test_phase_api_security.py`, `test_phase_api_profile.py`, `test_phase_api_dashboard.py`.

| Item | Status | Fix |
|---|---|---|
| API5 | ✅ | `/forgot-password` is a plain `def` (runs in the threadpool). Upload endpoints stay async but read at most limit+1 bytes, and Pillow / DB / Cloudinary work runs in `run_in_threadpool`. |
| API6 | ✅ | While *Enforce subscription expiry* is ON, `get_current_agent` returns 403 "subscription expired", with the same rule as Django (NULL expiry never expires; Paldi challengers keep access). `/agents/me`, logout, plans and plan-upgrade stay open so renewal works. Public profile and feature map are unchanged, matching Django (which only gates at the dashboard). |
| API7 | ✅ | Dashboard counts a subscription with NULL `expires_at` as active (as Django does). |
| API8 | ✅ | GET `/leads` returns an empty list (same shape, `is_locked=true`) when lead management is locked. |
| API9 | ✅ | Website/social links are validated with Django's URL rules (no `javascript:`) and saved under Django's keys (`linkedin`, …), so links edited in the app show on the public card again. Old keys are still read. |
| API10 | ✅ | City names validated (2–60 chars, letters, spaces, `.-'`), existing cities reused, max 5 new cities per agent per day. New cities stay active as before (there is no admin approval screen). |
| API11 | ✅ | The WAF still logs and blocks matches, but signed-in (valid, non-revoked token) users no longer count toward the 24h IP auto-ban. 64 KB scan cap; template-injection patterns bounded. |
| API12 | ✅ (partial) | Blocked IPs cached in memory for 60s (no DB session per request); rate-limit cache calls run in the threadpool. `LOWER(email)` kept: the Laravel tables' collation isn't recorded in the repo. |
| API13 | ✅ | Naive IST (`datetime.now()` / Python cutoffs) instead of UTC in account deletion, leads, device tokens, user tokens, dashboard month start and agent search. Other models with `utcnow` defaults (`agent_subscription`, `referral_code`, championship) are not written by the API in the audited paths. |
| API14 | ✅ | Unknown championship `ref_id` → 404 instead of the first participant. |
| API15 | ✅ | Public social-follow / scratch: `session_id` ≤ 64, `platform` ≤ 32 and must be one of the campaign's channels; repeat follows are not stored again. |
| API16 | ✅ | The feature map is computed once per request and reused by every feature check in that request. |
| API17 | ✅ | Referral codes use `secrets`, retry on a unique clash, and pick up a code a parallel request already created. |
| API18 | ✅ | Lead preferences: fees 0–10,000,000, percentages 0–100, null accepted (saved as 0); charging fields ≤ 50 chars. Career timeline POST/PUT use a schema (year 1950..next year, text caps). |
| API19 | ✅ | Removed unused `require_admin`, `create_refresh_token` and the broken `UserModel` login branch. |
| API20 | ✅ | Deletion OTP: never logged; if no email channel works the API returns 503 instead of a false success; hash is HMAC with `SECRET_KEY`. New daily `user-token-prune` job (`docs/CRON_JOBS.md`). |

Deploy notes: deletion OTPs issued in the 10 minutes before the deploy fail once (new hash). With expiry enforcement ON, the mobile app must show the new 403 message (not tested on a device). An admin unblocking an IP can take up to 60s to reach the API.

## Phase 6 status (2026-11-14) — big-file split

Pure moves, no logic change. Each original file stays as a façade that re-exports every old name, so URLs, imports and test patches keep working. Details and rules: `CLAUDE.md` → "Big view modules".

| File | Before | After | New modules |
|---|---|---|---|
| `apps/agents/views/registration.py` | 6,390 | 2,956 | `registration_common` (382), `_pricing` (853), `_fulfilment` (357), `_forms` (1,345), `_offers` (275), `_public` (433) |
| `apps/agents/views/dashboard.py` | 4,658 | 1,135 | `dashboard_common` (229), `_public` (578), `_profile` (1,513), `_leads` (441), `_account` (506), `_settings` (404) |
| `apps/home/views/pages.py` | 2,729 | 1,043 | `leads` (163), `homepage` (214), `agent_search` (482), `pincode` (230), `city_directory` (672) |

Checks run:
- Façade: every old name is still exposed (159 / 82 / 98), and every moved definition is the same object; `registration` defs also match the original bytecode.
- URL map: all 762 routes identical (path, name, view, order) against a baseline taken before the split.
- No import cycles: no submodule imports its façade; each imports cleanly on its own.
- `pyflakes` over the whole project: no undefined names, except one in dead code after a `return` in `wholesale/views/public_views.py` (never runs).
- `manage.py check` clean, no pending migrations, every file compiles.

Bug found during the split and fixed: `agent_dashboard` used `time.time()` without importing `time`. The `NameError` was swallowed, so every dashboard visit silently skipped the trial-activity log.

Still large (left on purpose): `apply_profile_update` (one ~975-line function, now in `dashboard_profile.py`) and the payment core in `registration.py`. Splitting those means changing logic, not moving it.

## Phase 5 status (2026-11-14) — safe structure work

| Item | Status | Change |
|---|---|---|
| CH15 | ✅ | `EventReferralParticipant.win_emailed_at` (migration `event_referral/0010`), set only after a successful send; re-runs email only those missed; `--force` re-sends. Migration `0011` backfills existing winners so nobody is emailed twice after deploy. |
| Unique-rule check | ✅ (tool) | New read-only `python manage.py audit_duplicates` reports duplicate reviews (agent + mobile), championship referrals (campaign + agent) and invoices (payment id). Run it on production; if all three are 0, the AG17 / CH4 / PAY13 unique migrations are safe. |
| INS-S | ✅ | One `create_onboarded_agent()` helper (`apps/insurance/services/onboarding.py`) replaces the 3 copied create blocks; a characterisation test checks every field each path creates, before and after. |
| WA-S | ✅ | `payment_callback` and the simulator page HTML moved into `templates/wa_agent_bot/` (−1,020 lines of Python). Output identical; simulator logs now use `safe_json`. |
| AG14 | ❗ Finding, nothing removed | The events signup is not dead: `register/` and `plans/` each appear twice in `urls_events.py`, so the form POST lands on the GET view and the registration/plan-choice code never runs. **Decision needed:** fix the routing (switches on a signup path never exercised in production) or retire the funnel. |

Not done in Phase 5 (high risk for little gain right now): splitting `registration.py` (6.3K lines), `apply_profile_update` and `pages.py`. Many tests patch names inside these modules, so a split needs its own careful change.

## Phase 4 status (2026-11-14) — remaining fixes outside FastAPI

FastAPI is still parked until the end. Two migrations, both index-only: `agents/0044_agent_leads_ip_created_idx` (AG9) and `wa_agent_bot/0008_message_log_phone_category_index` (WA13).

| Item | Status | Fix |
|---|---|---|
| WA3 (rest) | ✅ | The temp password is cleared from the bot session once the welcome message is delivered (kept only until a failed delivery is retried). |
| WA7 | ✅ | Incoming messages are processed under a row lock on the session, so a payment activation can't be overwritten. Edge case: a user message and a webhook arriving together can deadlock; MySQL cancels one, the webhook is retried and the user gets "try again". |
| WA11 | ✅ | Chatbot gets a per-chat-session daily cap and a warning at 80% of the global cap. Existing caps unchanged. |
| WA12 | ✅ | The LLM fallback chain stops trying more providers after a 25s total deadline. |
| WA13 | ✅ | Broadcast "already sent" check matches the exact phone; index migration; message logs older than 90 days are pruned by the background jobs (`wa-log-prune`, daily). |
| WA14 | ✅ | A plan change marks the old pending bot subscription failed and cancels its Razorpay link (best effort). The row and its order id stay, so a late payment on the old link still activates. |
| WA16 | ✅ | Phone numbers and emails are masked in bot logs. |
| WEB8 | ✅ (safe part) | find-agents no longer prefetches every review; rating and count come from two subqueries. Ranking and output unchanged. |
| WEB9 | ✅ | Search writes the session only when a value changes, and only stores a valid pincode or in-India coordinates. |
| WEB14 | ✅ | Contact and quick-lead limits count every attempt atomically; a hidden honeypot field drops bot posts silently. |
| custom_page | ✅ | One slug query instead of two. |
| JSON escapers | ⏸ Kept | The two page helpers also HTML-escape for `innerHTML`; swapping in `safe_json` would reopen XSS. |
| INS4 (reason) | ✅ | Rejection reason is appended to `agent.admin_notes` with a timestamp (no migration). |
| INS7 | ✅ | Variant payload is validated before anything is deleted; a DB error rolls back the whole product save. |
| INS10 | ✅ | Product pause/resume is POST with a CSRF token; buttons look the same. |
| INS12 | ✅ | Bulk import: 5 MB / 2000-row caps, case-insensitive `.csv`, SKUs/categories preloaded, unknown category = row error. A blank category still uses the default category as before. |
| INS16 | ✅ | Saving an invite message no longer creates a `users` row. |
| INS19 | ✅ | Distributor agent list pages in the DB; insurance agent and payment lists paginate (25/page); dashboard counts use one aggregate. |
| CH8 | ✅ | Unknown referral link redirects to the general championship page; tracking rows are written only for a valid ref, once per session. |
| CH9 | ✅ | Public Paldi leaderboard is cached for 45s and no longer builds referral lists (which held mobile/email). |
| CH11 | ✅ | A payment for a blocked referrer is recorded as paid-but-not-counting and counts after the participant is restored. |
| CH16 | ✅ | Slab counts in one aggregate; `select_related` on claims and recent referrals. |
| CH17 | ✅ (partial) | Leaderboard refresh is debounced to once per 30s, with no lost update. Ranks can be up to ~45s stale. Zero-referral participants are still ranked because dashboards show their rank. |
| CH15 | ⏸ Migration | Needs an "emailed" field on the participant. |

## Section 3 close-out (2026-11-13): agents dashboard / profile / public

| Item | Status | Fix | Test |
|---|---|---|---|
| AG1, AG2, AG3, AG4, AG6, AG12, AG15, AG16, AG20 | ✅ | Fixed in Phases 0–3. | – |
| AG5 | ✅ | A profile save that fails validation now rolls back the whole save (`transaction.set_rollback(True)` before each of the 12 error returns). The 500 reply no longer shows `str(e)`. | `agents/test_section3_dashboard.RejectedProfileSaveWritesNothingTests` |
| AG8 | ✅ | Dashboard lead list shows the newest 500 leads, not every lead ever. | – |
| AG10 | ✅ (scoped) | Chromium already ran one at a time with a Pillow fallback, and hidden agents 404 since AG3. Added a 10s timeout on `set_content`. | – |
| AG11 | ✅ (scoped) | Bio generation stops starting new LLM attempts after 45s. Each attempt's provider chain is in `chatbot/llm_client.py` (WA12, chatbot section). | – |
| AG17 | ✅ (partial) | Review rate limit uses atomic `cache.add`/`incr`. A unique constraint on (agent, reviewer_mobile) needs a migration and a duplicate clean-up first — not done. | `ReviewRateLimitTests` |
| AG18 | ✅ | A slug collision on insert retries once with a random suffix instead of failing the signup. | `SlugRaceTests` |
| AG19 | ✅ | The lead FCM and lead email threads close their DB connection when done. | `ThreadConnectionCleanupTests` |
| AG7 | ⏸ Needs a check | Professional-only profile fields may be saved by a lower plan through a direct POST (UNVERIFIED). Needs a plan-vs-field decision. | – |
| AG9 | ⏸ Migration | `(ip_address, created_at)` index on `AgentLead` — needs a migration, best applied with the other indexes in one deploy. | – |
| AG14 | ⏸ Dead code | The unreachable events signup (~1000 lines) is left in place; the webhook fulfilment in that file is still used. Removal belongs to Phase 5. | – |
| AG-S | ⏸ Phase 5 | Splitting `apply_profile_update` (975 lines) and `agent_dashboard` (775 lines). | – |

## Section 2 close-out (2026-11-13): agents registration / payment / auth

Kept out of scope by the owner: registration OTP, and anything that changes the login id / password scheme (so PAY8 and PAY14 stay as they are).

| Item | Status | Fix | Test |
|---|---|---|---|
| PAY1–PAY7, PAY9, PAY11, PAY15 | ✅ | Fixed in Phases 0–3 (see those tables). | – |
| PAY10 | ✅ | Retries already ran only for a genuine payer. Added: anonymous `/agent-register/payment-callback/` is capped at 20/min per IP; the payer's own checkout session is never limited. | `agents/test_pay_section2.PaymentCallbackRateLimitTests` |
| PAY12 | ✅ | `_activate_paid_subscription` locks and re-reads the agent before saving, so an admin approval or profile edit made in between is kept. | `ActivationReReadsAgentTests` |
| PAY13 | ✅ | Renewal price uses the same whole-rupee GST bundle as signup (₹2359, not truncated 2358.81). Invoice base/GST split uses Decimal. | `RenewalPriceTests`, `InvoiceSplitTests` |
| PAY16 | ✅ (scoped) | The gate middleware looks the agent up once per request (was twice on dashboard pages). Not cached across requests, so a restriction or new payment applies on the next click. | `GateResolvesAgentOncePerRequestTests` |
| PAY-S | ✅ (small) | One `_clear_checkout_session()` helper replaces 4 copied blocks; duplicate `csrf_exempt` import removed; `agent_register_complete` returns 500 (not 200) on an unexpected error — the page reads the JSON either way. | existing e2e tests |
| PAY8, PAY14 | ⏸ Owner decision | Both concern the login password scheme, which stays unchanged. | – |

Not done: splitting `registration.py` (6.3K lines) into modules. That is the Phase 5 structure work; doing it now would mix a large move with these behaviour fixes.

Renewal price note: renewals now cost the same rounded total as a new signup (₹2359 for a ₹1999 plan, ₹11799 for ₹9999) instead of ₹2358.82 / ₹11798.82.

## Phase 3 status (2026-11-13) — quick fixes

FastAPI items are still parked until the end, at the owner's request. Each fix has a test in that app's `test_phase3_quick.py`. No migrations.

| Item | Status | Fix |
|---|---|---|
| WA6 | ✅ | The Razorpay event is marked processed only after activation succeeds, so a failed activation can be retried. |
| WA10 | ✅ | Group, `@lid` and broadcast chat ids are ignored; only personal chats reach the bot. |
| WA15 | ✅ | The bot simulator returns 404 in production (DEBUG off). |
| WA17 | ✅ | One neutral reply instead of "account with email/mobile X already exists". |
| PAY9 | ✅ | An agent login never changes a distributor's or insurance user's `users.role`. |
| PAY15 | ✅ | The promo use count is a conditional UPDATE, so it can't pass `max_uses`. A paid order after the cap still goes through. |
| AG4 | ✅ | The lead email escapes customer fields; leads are capped at 5 per 10 minutes and 20 per day per IP+agent (same limits as the card form). |
| AG12 | ✅ | `/events/verify-promo/` pauses after repeated wrong codes, like the signup check. |
| AG15 | ✅ | Only the notifications actually shown are marked read. |
| AG16 | ✅ | Career timeline returns 404 JSON instead of 500 for an admin with no agent. |
| AG20 | ✅ | The lead-email link uses `APP_URL` instead of a hard-coded domain. |
| WEB7 | ✅ | Quick-lead phone: "+91 98765 43210" → 9876543210; must be a valid Indian mobile. A bad email is rejected. |
| WEB10 | ✅ | Search analytics / "card seen" alerts only run for a valid 6-digit pincode (or no pincode). |
| WEB11 | ✅ | City pages stop counting at 3 or 5 rows; the page is unchanged. |
| WEB13 | ✅ | Bad banner/popup JSON is cached as `{}`, so the DB is not hit on every page. |
| WEB16 | ✅ | Removed the unreachable `seo.robots_txt` view and route. |
| INS4 | ✅ (partial) | Approve/reject only for `pending_manager_approval`. The rejection reason is not saved: that needs a new column. |
| INS6 | ✅ | Editing an approved/published/paused product sends it back to admin review. |
| INS8 | ✅ | Distributor password change uses `check_password_hash`; no match → refused; missing fields no longer crash. |
| INS9 | ✅ | `_distributor_laravel_id` returns None with no `users` row; every caller denies. |
| INS11 | ✅ | RFQ, price API and cross-sell open only published products from approved wholesalers; a variant must belong to its product. |
| INS13 | ✅ | RFQ quote is a Decimal > 0 (no NaN or infinity). |
| INS14 | ✅ | `record_payment`, `checkout_online_success` and `save_invite_message` log the error and show a generic message. |
| INS15 | ✅ | `notify_send` is manager-only; `request_status_change` is manager/onboarding and only accepts activate/deactivate. |
| INS17 | ✅ | Removed the `session['wholesaler_id']` / raw `session['admin_id']` auth fallbacks. |
| INS18 | ✅ | The wholesale product wizard and categories page escape what they put on the page. |
| CH5 | ✅ | A refund recount locks the referrer row first. |
| CH6 | ✅ | "Freeze leaderboard" now stops re-ranking. |
| CH7 | ✅ | Blocked participants are removed from the leaderboard cache. |
| CH10 | ✅ | Self-referral compares the last 10 digits (+91 / 0 handled). |
| CH12 | ✅ | `_grant_win` leaves suspended, blacklisted and rejected agents blocked. |
| CH13 | ✅ | Claim updates are locked; delivered/redeemed can't move back. |
| CH14 | ✅ | The Paldi activity CSV uses `safe_csv_writer`. |

Still open from this batch, both needing a decision:
- The distributor `dashboard` view still falls back to `auth_user.id` when no `users` row exists. In practice that is only superusers, and removing it could lock them out.
- Moving a delivered claim to cancelled/expired is still allowed.

## Phase 2 status (2026-11-13)

FastAPI items are parked until the end, at the owner's request.

| Item | Status | Fix | Test |
|---|---|---|---|
| PAY11 / AG6 / WEB12 / CH18 (invariant 5) | ✅ Fixed | Every JSON value printed into a `<script>` now uses `safe_json`: `dashboard.html` (4), `edit_profile.html` (2), `review_share_popup.html`, `home.html`, `calculators/detail.html`, `referral_championship/agent_dashboard.html`. | existing page tests |
| PAY7 | ✅ Fixed | The ₹0 checkout now calls `_activate_paid_subscription`, the same path the webhook, callback and recovery use. | `agents/test_promo_accounting.py`, `test_registration_e2e.py` |
| PAY6 | ✅ Fixed | A `refunded` subscription is final: activation and the webhook leave it alone. | `agents/test_signature_replay.RefundedIsFinalTests` |
| INS3 | ✅ Fixed | `record_payment` keeps the subscription's own order id; the UTR stays on `agent.payment_reference`. One existing test was updated to match. | `insurance/test_offline_payment_reference.py` |
| WA4 | ✅ Fixed (scoped) | The poll and callback paths activate only when the payment link is `paid` **and** `amount_paid` equals the priced amount. The poll path now stores the payment id. | `wa_agent_bot/test_payment_hardening.PaymentLinkPaidInFullTests` |
| WA5 | ✅ Fixed | WhatsApp messages are sent after the DB commit, not while the subscription row is locked. | `test_payment_hardening.test_whatsapp_send_waits_for_commit` |

Not done in WA4: the bot still has its own activation function instead of calling `_activate_paid_subscription`. Its rules differ (no championship or Paldi hooks, its own password and session steps), so merging them is a Phase 5 refactor.

## Phase 1 status (2026-11-12)

| Item | Status | Fix | Test |
|---|---|---|---|
| PAY5 | ✅ Fixed | Recovery now checks every open order in the last 30 days (was the newest 5). | `agents/test_orphan_paid_orders.test_recovery_finds_paid_order_older_than_five_retries` |
| AG3 | ✅ Fixed | Suspended / deleted / unpaid agents' public profile, review, lead-capture and OG-image endpoints 404. The owner and admin paths still open. | `agents/test_hidden_agent_public.py` |
| WEB3 | ✅ Fixed | Public `pincode_fetch` is capped at 30/min per IP and misses are cached for 24h. | `home/tests/test_pincode_and_geocoding_limits.py` |
| WEB4 | ✅ Fixed | `save_user_location` reverse-geocodes only when the point is inside India, and at most one lookup per IP per minute. NaN/out-of-bounds are dropped. | same |
| WEB5 | ✅ Fixed | `pincode_fetch` no longer overwrites `Pincode.office_name` with Nominatim's display string. | same |
| API2 | ✅ Fixed | OTP request returns one generic message for unknown email, wrong PAN, wrong phone. Path added to `SENSITIVE_PATH_MARKERS`. | `fastapi_app/test_deletion_enum_and_reset.py` |
| API3 | ✅ Fixed | In-app password change revokes every other `UserToken` jti but keeps the caller's own jti alive, so their current token still works. Emailed-token resets still revoke everything. | same |
| API4 | ✅ Fixed | Reset with an unknown email returns the same "invalid or expired token" message as a bad token. | same |
| WA2 | ✅ Fixed | The `credentials` reply now sends a reset link instead of "password = your mobile". | `wa_agent_bot/test_credentials_and_redaction.py` |
| WA3 | ✅ Fixed (partial) | `WaBotMessageLog` now redacts any "Password:" line before storing. The "Set your password" link replaced the plaintext password in the payment-received reply, too. `registration_data.temp_password` and `generated_password` are still written; audit reports will tackle those in Phase 2 with a schema change. | same |
| WA4 | ⏸ Deferred | Needs the bot's own activation path to route through `_activate_paid_subscription` and share `ensure_payment_captured`. Touches the webhook, poll and callback paths together; larger refactor. | – |
| WA5 | ⏸ Deferred | Send OpenWA messages after `on_commit` instead of inside the `select_for_update` lock. Blocked by WA4. | – |
| AG2 | ✅ Fixed | Only reviews written by a logged-in client count toward feature unlock. The public card still shows every approved review. | `agents/test_review_unlock_requires_verified.py` |
| INS1 | ✅ Fixed | Insurance bulk offline checkout now validates the UTR, payment method and date (no Razorpay prefixes, no future dates, method from a whitelist). It also stops writing the UTR into `razorpay_order_id`, matching invariant 9. | covered by `insurance` tests (role matrix) |
| CH3 | ✅ Fixed | On revert, in-flight claims (`unlocked` / `verification` / `approved` / `processing`) for slabs the agent no longer qualifies for are cancelled. Paid-out states (`dispatched` / `delivered` / `redeemed`) are left alone. | `referral_championship/test_claim_withdrawal.py` |
| INS14 | ✅ Fixed (partial) | `checkout_cart` no longer leaks `str(e)` to clients; returns a generic 500. The other three leak sites are still open. | – |

Residual risk: WA4/WA5 cover the bot activation path going around the shared Django activation. An attacker who can forge Razorpay webhooks still can't abuse it (HMAC + captured check are in place), so this stays Phase 2.

## Phase 0 status (2026-11-12)

| Item | Status | Fix | Test |
|---|---|---|---|
| WA1 | ✅ Fixed | The bot refuses any email that already has an Agent or a login it did not create. A plan change by the same session still works. The user is sent back to the email question. | `wa_agent_bot/test_account_takeover.py` |
| PAY1 | ✅ Fixed | A browser that does not own the checkout can continue an unpaid registration only with the original mobile, so it can no longer swap in its own mobile (which becomes the first password). | `agents/test_step1_reuse_takeover.py` |
| PAY2 | ✅ Fixed | A Razorpay signature signs the payer in once, and only within 1 day of the order. | `agents/test_signature_replay.py` |
| PAY3 | ✅ Fixed | Replaying an older order no longer changes `plan_type` or deactivates the newer subscription. | same |
| PAY4 | ✅ Fixed | A new renewal deletes only abandoned rows that have no order id. Rows with an order id stay, so a late payment on them can be matched. | `agents/test_renewal_orders.py` |
| WEB1 | ✅ Fixed | `all_claim_companies\|safe_json` | template change |
| AG1 | ✅ Fixed | The GBP URL must be `http(s)` on a Google host. The public profile JS also refuses `javascript:`/`data:` links already saved. | `agents/test_gbp_url_validation.py` |
| WEB2 | ✅ Fixed | Added `/api/quick-lead-capture/` and `/api/google-review/` to `DJANGO_API_PREFIXES`, plus a test that checks every Django `api/` URL. | `home/tests/test_api_routing.py` |
| CH1 | ✅ Fixed | `get_current()` returns the latest campaign instead of re-creating it (Django and FastAPI). | `referral_championship/test_campaign_lifecycle.py` |
| CH2 | ✅ Fixed | `offer_is_open()` (live and before `end_date`) gates the campaign price on all 3 checkout paths. | same |
| API1 | ✅ Fixed | Reference ids now carry 64 random bits. `/status` masks name, email and mobile, never returns admin notes, and the status card escapes every value. | `fastapi_app/test_account_deletion_status.py` |
| INS2 | ⏸ Not changed | The sidebar deliberately shows "Payments Queue" to the sales role, so sales access looks intended. **This is your call.** | – |

Residual risk on PAY1: someone who knows both the email and the mobile can still continue the registration. The real fix is an email OTP, or a set-password link instead of mobile-as-password (theme 4).

---

## 1. WhatsApp bot + chatbot (`apps/wa_agent_bot`, `apps/chatbot`)

**Done well**
- The inbound webhook fails closed and compares secrets with `compare_digest`.
- The Razorpay webhook checks the HMAC, requires a captured payment and matches the amount.
- `payment_callback` asks Razorpay itself instead of trusting query parameters.
- Chatbot history is owned by the server, with an Origin check, length caps and spend caps.

| # | Sev | Where | Issue | Fix |
|---|---|---|---|---|
| WA1 ✅ | **Critical** | `services/payment_service.py:172-212` | **Account takeover.** `create_or_update_pending_agent` runs `User.get_or_create(username=email)` and then `set_password()` on whatever row it finds, including staff, insurance and distributor users, before any payment. It also takes over another person's `pending_payment` agent (changes the mobile, resets the password). After payment, the credentials go to the attacker's WhatsApp. | Refuse when a User or Agent already exists for the email. The correct guards already exist in the unused `registration_handler.create_agent_from_wa_data` (`:89-111`). Never call `set_password` on a user this flow did not create. Add a regression test. |
| WA2 | High | `post_login_handler.py:268-285`, `state_machine.py:720-736` | The "credentials" command and the "payment received" reply say the password is the mobile number. Bot signups actually get a random `temp_password`, so the login fails. | Send a reset link instead. |
| WA3 | High | `payment_service.py:367,526-529`, `message_sender.py:66` | The temporary password is stored in plaintext in `registration_data`, `generated_password` and `WaBotMessageLog.content`, all visible in admin and in backups. | Do not store it. Redact the credentials line before logging. |
| WA4 | High | `payment_service.py:402`, `state_machine.py:704-707`, `views.py:510-519` | Bot activation does not go through `_activate_paid_subscription` (invariant 10). The poll and callback paths only check `link.status=='paid'`: no `ensure_payment_captured`, no amount check. | Route all three paths through `ensure_payment_captured` plus the amount check plus `_activate_paid_subscription`. |
| WA5 | High | `payment_service.py:539-560` | Up to two OpenWA sends (≈60 s each) run inside `atomic()` while holding `select_for_update`. | Send after commit (`transaction.on_commit`). |
| WA6 | Med | `views.py:411-418` | The Razorpay event id is cached *before* processing. If activation fails, Razorpay retries are ignored for 24 h. | Use `cache.add`, and set the key only after success. |
| WA7 | Med | `views.py:255-297` | The session is saved without locking. A concurrent payment webhook's `logged_in` state is overwritten back to `awaiting_payment`. | `atomic()` + `select_for_update()` on the session row. |
| WA8 | Med | `state_machine.py:473-541`, `payment_service.py:494-515` | The mobile typed by the user is never verified, and the credentials are sent to whatever WhatsApp session matches it. | Register only the sender's own number; send credentials only to `session.phone_number`. |
| WA9 | Med | `views.py:74-77` | The webhook secret is passed as `?token=` in the URL, so it can end up in access logs (UNVERIFIED that it does). | Strip it from the logs, rotate it, and use a header or HMAC if OpenWA supports one. |
| WA10 | Med | `views.py:96-118` | Group (`@g.us`) and `@lid` chat ids are reduced to digits and treated as phone numbers, so credentials can be sent into a group. | Ignore anything that is not `@c.us` / `@s.whatsapp.net`. |
| WA11 | Med | `chatbot/views.py:243-249` | Limits are 100 per IP and 5000 per day globally, so about 50 rotating IPs switch the chatbot off for everyone. | Add a per-session cap and a challenge after N messages. |
| WA12 | Med | `chatbot/llm_client.py:504-646, 1435+` | The provider fallback can take 8 providers × 12 s × 2 attempts. `executor.shutdown(wait=False)` leaks threads. | Add a total deadline of about 20 s and use the SDK timeout. |
| WA13 | Med | `broadcast.py:256-267` | The `already_sent` check runs `endswith` + content LIKE on an unpruned log, once per recipient. | Add an index, match the exact phone, and prune old logs. |
| WA14 | Med | `payment_service.py:280-286` | Every "change plan" creates a new subscription, payment link and password. The old links can still be paid. | Reuse or cancel the open link. |
| WA15–17 | Low | `simulator_views.py`, logs, `state_machine.py:405-416` | The simulator creates real rows and payment links in production; phone numbers appear in INFO logs; replies reveal whether an email is registered. | Gate the simulator to DEBUG, mask phones, use generic messages. |
| WA-S | Struct | | Very long functions: `simulator_page` (623 lines), `payment_callback` (508), `stream_plain_text_completion` (423), `_execute_find_agents` (340). The provider loop is duplicated. `create_agent_from_wa_data` is dead code. | Move the HTML into templates and share one provider loop. |

## 2. Agents: registration, payment, auth (`apps/agents`)

**Done well**
- The webhook always checks the HMAC.
- `_activate_paid_subscription` locks the row, is idempotent, runs side effects in savepoints and starts fulfilment with `on_commit`.
- Only captured payments are accepted, with server-priced paise compared.
- Background jobs use `cache.add` plus a MySQL named lock.

| # | Sev | Where | Issue | Fix |
|---|---|---|---|---|
| PAY1 | High | `views/registration.py:2522-2614, 3579-3596`, `services/account_auth.py:432-443,534` | Step 1 is unauthenticated and reuses any `incomplete`/`pending_payment`/`rejected` agent with the same email. It overwrites `mobile`, which becomes the first password, and binds this browser to the victim's draft. When the victim's order is captured later, the attacker logs in with their own mobile. A ₹0 promo signs them in at once (`:4722`). | Reuse the agent only when the session owns it, or after an email OTP. Never change the mobile without proof. |
| PAY2 ✅ | High | `registration.py:4858-4879, 5068-5105`, `plans.html:3229` | A valid Razorpay signature signs the caller in, forever and repeatedly. The callback is a CSRF-exempt GET, so the signature ends up in URLs, browser history and Referer headers. | Allow one signature login per order, within about 30 minutes of capture. |
| PAY3 ✅ | High | `registration.py:4869-4876` | Replaying an old completed order re-syncs `plan_type` to that order and deactivates the other subscriptions, so Professional drops to Starter. | On an already-completed order: log in and redirect only. |
| PAY4 ✅ | High | `views/renewal.py:97-101` | A new renewal deletes the previous pending renewal *including its Razorpay order id* (breaks invariant 9). A late payment then finds no row: the webhook returns 503 and Razorpay retries for 24 h, and recovery ignores `renew-` receipts. | Never delete a row that has an order id. Teach the adopt and recovery paths about `renew-`. Add renewal tests. |
| PAY5 ✅ | Med | `registration.py:4133` | Recovery checks only the newest 5 orders (`[:5]`), which breaks invariant 9. | Filter by the last 30 days instead. |
| PAY6 | Med | `registration.py:3934, 5893` | A `refunded` subscription is not treated as final and can be re-activated by a re-delivered webhook (UNVERIFIED trigger). | Treat `refunded` as final. |
| PAY7 | Med | `registration.py:4668-4712` | The ₹0 checkout copies the activation logic (breaks invariant 10) and skips the upgrade, renewal and event handling. | Call `_activate_paid_subscription`. |
| PAY8 | Med | `account_auth.py:288-294, 531-535` | A legacy PBKDF2-only user gets their password reset to the mobile number on activation (UNVERIFIED that such users exist). | Overwrite only when there is no usable hash. |
| PAY9 | Med | `account_auth.py:499-500`, `views/auth.py:303` | `sync_verified_password(role='agent')` can change a distributor's or insurance user's `users.role` to agent (UNVERIFIED). | Pass `role=None` for non-agent roles. |
| PAY10 | Med | `registration.py:5099-5110, 1116-1128` | The anonymous `payment_callback` sleeps about 7.5 s and makes up to 6 Razorpay calls, with no rate limit. | Rate-limit by IP, drop the sleeps, and let the webhook finish activation. |
| PAY11 | Med | `dashboard.html:2614,2737,2769`, `edit_profile.html:5432-5435`, `review_share_popup.html:697` | JSON is printed with `\|safe` inside `<script>` (breaks invariant 5). `studio_templates_json` (`invite_studio.py:455`) is admin-configured and does not escape `</`. | Use `\|safe_json` everywhere. |
| PAY12–16 | Low | | Activation saves a stale agent object (`:4003`). `Invoice.razorpay_payment_id` is not unique, GST is computed with floats, and renewal paise are truncated with `int(total*100)`. The welcome email always claims the password is the mobile. The promo `max_uses` check can race. The payment-gate middleware runs 4-6 queries per request. | `update_fields` + lock, Decimal + unique constraint, conditional promo UPDATE, cache the gate in the session. |
| PAY-S | Struct | | `registration.py` is **6,317 lines**. Longest functions: `register_step1` (546), `_agent_register_complete_impl` (~530), `chooseplan` (474), `_finalize_razorpay_payment` (232), `create_agent_from_draft` (220). The session-pop block is copied 4 times. `agent_register_complete` returns 200 on an exception. No tests cover renewal, step-1 reuse or signature replay. | Split into `registration/{steps,checkout,finalize,recovery}.py`. |

## 3. Agents: dashboard, profile, public pages (`apps/agents`)

**Done well**
- `serve_private_file` normalises the path first (invariant 7).
- An email change rejects addresses already owned by another account (invariant 6).
- `agent_card_lead_submit` is a good model: it escapes output, uses atomic rate limits and hides suspended agents.
- Uploads are checked by magic bytes and re-verified with PIL.

| # | Sev | Where | Issue | Fix |
|---|---|---|---|---|
| AG1 ✅ | High | `views/gbp.py:153-165, 433`, `profile-content.html:1358` | **Stored XSS.** The GBP URL check is an unanchored `re.search`, so `javascript:…//maps.google.com` passes and is opened by `window.open(url,'_self')` for every visitor. | Parse the URL, require `https`, and allowlist the hostname. |
| AG2 | High | `dashboard.py:1444-1620`, `review_growth.py:266` | Anonymous reviews are auto-approved with an unverified mobile, and they count toward the paid-feature unlock thresholds. Three fake reviews unlock Professional features. | Count only verified or admin-approved reviews. |
| AG3 ✅ | High | `dashboard.py:1292, 1444, 3636, 4013` | The public profile, review, lead-capture and OG-image views never call `_hidden_from_public`, so suspended or deleted agents stay public and keep collecting leads. | Apply the same check the card views use. |
| AG4 | Med-High | `dashboard.py:3634-3955` | `agent_capture_lead` (CSRF-exempt) puts unescaped fields into the agent's HTML email. The rate limit counts distinct agents per IP, so one agent can be flooded. | `html.escape` + `add`/`incr` limits, as in `agent_card_lead_submit`. |
| AG5 | Med | `dashboard.py:2210+` | `apply_profile_update` returns 422 *inside* `atomic()`, so the step-1 changes are already committed. It also returns `str(e)` at `:3138`. | Raise inside the block and convert to 422 outside it. |
| AG6 | Med | `dashboard.html:2707` | Notification bodies are shown as raw HTML in SweetAlert. | Escape them. |
| AG7 | Med | `dashboard.py:1946/2176` | Professional-only profile fields are not plan-checked on the server (UNVERIFIED impact). | Check feature keys for each step. |
| AG8 | Med | `dashboard.py:498` | The dashboard renders every lead, with no limit. | Paginate. |
| AG9 | Med | `models.py:1382`, `dashboard.py:3697` | The lead rate-limit query has no `(ip_address, created_at)` index, so it scans the full table. | Add the index. |
| AG10 | Med | `og_image.py:334-356` | A cold OG image starts Chromium inside the request; the ids are sequential and public. | Use Pillow in the request and Chromium only in prewarm. |
| AG11 | Med | `bio_generator.py:377-425` | AI bio generation can block for 3 × 35 s × the number of providers. | Cap the total at about 30 s, or run it in the background. |
| AG12–19 | Low | | `/events/verify-promo/` has no rate limit. The events signup is unreachable (duplicate paths, about 1000 dead lines). Notifications are marked read with a race. `career_timeline` returns 500 for an admin with no agent, and admin-on-behalf skips RBAC. Duplicate reviews are possible (no unique constraint). The slug can race. Threads leak DB connections. The domain is hard-coded at `dashboard.py:3963`. | See the agent notes; each is a one-line fix. |
| AG-S | Struct | | Longest functions: `apply_profile_update` (**975** lines), `agent_dashboard` (775), `public_agent_card` (380), `agent_capture_lead` (376), `agent_upgrade_plan` (337). There are two lead endpoints with different hardening and three ways of resolving the current agent. The slug lookup is repeated 4 times. | Split into a step-per-function form service and merge the lead endpoints. |

## 4. FastAPI (`fastapi_app`)

**Done well**
- IDOR is consistently prevented (every query is filtered by `current_agent.id`).
- JWTs carry a jti and are checked for revocation; HS256 is pinned; the default secret is refused in production.
- The reset token is bcrypt-hashed and the reset host comes from config.
- Login is throttled.
- Uploads are checked by magic bytes and re-encoded.

| # | Sev | Where | Issue | Fix |
|---|---|---|---|---|
| API1 ✅ | High | `routers/account_deletion.py:321, 174` | `/status/{ref}` has no authentication and returns email, mobile, name and admin notes. The ref is `DEL-date-` + 6 hex digits, about 16.7M values per day. | Require the email together with the ref (or a signed token) and use 16+ random bytes. |
| API2 | High | `account_deletion.py:148,157` | The OTP request gives different answers for an unknown email, a wrong PAN and a wrong phone, and it is not in the sensitive-path rate limit. | One generic message; add the path to `SENSITIVE_PATH_MARKERS`. |
| API3 | High | `services/password_reset_service.py:247-253` | Changing the password in the app does not revoke other tokens, so a stolen token lives up to 120 minutes. | Revoke every other jti. |
| API4 | Med | `password_reset_service.py:199` | Reset replies "email not registered", which reveals who has an account. | Use a generic message. |
| API5 | Med | `routers/profile.py:145,208,458,513`, `auth.py:95` | Blocking DB, Pillow and Cloudinary work runs inside `async def`, and whole files are read before the size check. | Make these plain `def` endpoints; stream with a size cap. |
| API6 | Med | `dependencies/auth.py:76`, `lock_unlock_service.py:444`, `public_profile_service.py:40` | Subscription expiry (invariant 12) is not enforced in the API. | Add the check in `get_current_agent`. |
| API7 | Med | `dashboard_service.py:59` | "Active subscription" drops NULL `expires_at`, unlike Django's `still_valid_q`. | Treat NULL as still valid. |
| API8 | Med | `routers/leads.py:36-56` | `GET /leads` returns lead PII even when `lead_management` is locked. | Return empty, or gate it. |
| API9 | Med | `profile_service.py:764,1104-1105` | Social URLs are not validated (`javascript:` accepted) and are saved under different keys (`linkedin_url` vs `linkedin`), so links edited in the app disappear from the public card. | Reuse `normalize_web_url` and Django's key names. |
| API10 | Med | `profile.py:644-688` | Any agent can create unlimited active global `City` rows. | Validate, create inactive for review, rate-limit. |
| API11 | Med | `middleware/threat_monitor.py:24-33,200` | The WAF regexes scan free-text JSON. Three hits ban the IP for 24 h (risk for shared mobile IPs; UNVERIFIED how often it fires). | Skip authenticated free-text fields, or only log on API routes. |
| API12 | Med | `threat_monitor.py:147`, `user_repository.py:10`, `agent_repository.py:14` | Every request opens an extra DB session for blocked IPs, runs sync cache I/O on the event loop, and uses `LOWER(email)` (no index use), on a 5-connection pool. | Cache blocked IPs in memory; use plain equality. |
| API13 | Med | `agent_lead_repository.py:81`, `account_deletion.py:30`, `agent_device_token_repository.py:24`, `dashboard_service.py:49`, `agent_search_service.py:178` | **UTC written into naive-IST columns**, so leads appear 5.5 h off and monthly counts shift. | Use `datetime.now()` / `NOW()` as Django does. |
| API14–20 | Low | | An unknown championship ref falls back to the first participant. Public social-follow / scratch endpoints are unbounded. The feature map is recomputed on every gate check (about 8 queries). The referral code races to a 500. Lead preferences are unbounded and `null` crashes. There is dead auth code (`require_admin` without jti, `create_refresh_token`, `UserModel` import). The deletion OTP is logged in plaintext, `user_tokens` is never pruned, and ORM threads skip `close_old_connections`. | Each is a small fix. |
| API-T | Tests | | Only 5 test files; nothing covers revocation, IDOR, uploads, deletion enumeration or the public championship endpoints. | Add tests for API1–API3 first. |

## 5. Public site + config (`apps/home`, `padosi_agent/`)

**Done well**
- `SECRET_KEY` has no fallback, `DEBUG` defaults to off, and HSTS and secure cookies are set.
- `get_client_ip` only trusts proxy headers from the right sources.
- `serve_public_media` is safe, and `clean_html` is used for CMS HTML.
- Pincodes are checked with a regex before any external call (no SSRF).

| # | Sev | Where | Issue | Fix |
|---|---|---|---|---|
| WEB1 ✅ | High | `views/pages.py:486-543`, `find-agents.html:2330` | **Stored XSS.** `{{ all_claim_companies\|safe }}` prints a Python list inside `<script>`. The values are free text typed by agents (`agents/views/dashboard.py:2563`) and cached for 30 minutes for every visitor. | `\|safe_json`, plus a whitelist of companies on save. |
| WEB2 ✅ | High | `padosi_agent/api_routing.py:12-16` | `/api/quick-lead-capture/` and `/api/google-review/track-click/` are missing from `DJANGO_API_PREFIXES`, so production sends them to FastAPI, which returns **404**. All exit-popup leads and review clicks are lost. Tests use Django's client and miss this. | Add both prefixes, plus a test that checks every Django `api/` URL against `is_fastapi_path`. |
| WEB3 | High | `pages.py:1098-1167,1197`, `services/geocoding.py:155-200` | Public `pincode_fetch` has no rate limit; each call can do 3 × (1 s + 5 s) of external lookups; failures are not cached. Workers can be exhausted and OSM may ban the IP. | Per-IP limit, cache misses for a day, a single attempt. |
| WEB4 | High | `pages.py:1882-1903`, `geocoding.py:397-443` | `save_user_location` reverse-geocodes any lat/lng (NaN, outside India) with no throttle. | Check bounds and rate-limit. |
| WEB5 | Med | `pages.py:1148-1153` | A public GET overwrites `Pincode.office_name` and blanks `district`. | Never write to the table from this view. |
| WEB6 | Med | `pages.py:1447-1448`, `middleware.py:121` | Raw-HTML CMS pages are served unsanitised with a weak CSP. | Serve them with a sandbox CSP. |
| WEB7 | Med | `pages.py:2617-2630` | Quick-lead phone `+91 98765 43210` becomes `9198765432` (wrong number). | Strip `91`/`0`, then require exactly 10 digits starting 6-9. |
| WEB8 | Med | `pages.py:544-770, 1813` | find-agents loads every match with 7 prefetches and then slices in Python; AI picks repeats the same query. | Cache the sorted id list and fetch only the page. |
| WEB9 | Med | `pages.py:840-885` | Every search writes the session (a DB write). | Write only when the value changes. |
| WEB10 | Med | `pages.py:1044-1061` | Any GET starts an analytics thread plus WhatsApp "card seen" alerts, with an unchecked pincode. | Validate and rate-limit. |
| WEB11 | Med | `pages.py:2367,2423` | City pages run `count()` twice on a heavy queryset. | Use `len()` of the capped list. |
| WEB12–15 | Low | | Calculator JSON-LD is printed with `json.dumps\|safe`. The context processor caches `None`, so the DB is hit on every request. The lead-form rate limit can race and has no honeypot. The homepage review cache is stale for 30 minutes. | `safe_json`, cache `{}`, `incr` + honeypot. |
| WEB-S | Struct | | `pages.py` is 2,651 lines. Longest functions: `find_agents` (282), `city_agents_directory` (281), `fetch_filtered_agents_list` (223), `_resolve_area_to_pincodes` (193), `build_agent_query` (177, with 12 parameters). `seo.robots_txt` is dead (shadowed by a `TemplateView`). There are 3 different JSON escapers. | Split into `views/{search,city,pincode}.py` and keep only `safe_json`. |

## 6. Insurance, distributors, wholesale

**Done well**
- Sub-distributor auth follows CLAUDE.md and is tested.
- Online insurance payments are solid: captured check, amount check, row locks.
- All portal logins are throttled.
- Ownership is scoped consistently.

| # | Sev | Where | Issue | Fix |
|---|---|---|---|---|
| INS1 | High | `insurance/views/agents.py:307-383` | Offline `checkout_cart` skips the `record_payment` checks (`pay_`/`order_` refs, future dates), writes the UTR into `razorpay_order_id` and `razorpay_payment_id`, and shares one order id across the whole cart (breaks invariant 9). | One shared offline-payment validator; never put UTRs in `razorpay_*`. |
| INS2 ✅ | High | `insurance/decorators.py:33` | `insurance_manager_or_accounts_required` also lets **sales** in, giving access to `record_payment` and the Razorpay order and success endpoints. | Remove `is_insurance_sales()` from it. |
| INS3 | Med | `insurance/views/payments.py:104` | `record_payment` overwrites the subscription's order id with the UTR; there is no amount and the method is free text. | Keep the order id; store the UTR in `payment_reference`. |
| INS4 | Med | `insurance/views/approvals.py:26,40` | Approve and reject have no status check, so an active agent can drop back to pending payment and be paid twice. The rejection reason is lost. | Require `pending_manager_approval`. |
| INS5 | Low (by design) | `insurance/views/agents.py:122,340,511` | New users are created with `password=email`. CLAUDE.md invariant 3 explicitly allows this for insurance onboarding, so it is a business decision, not a bug. Email addresses are easy to guess, though. | Your call: a random password plus a reset link. |
| INS6 | Med | `wholesale/views/wholesaler_views.py:113-117` | Editing an approved product keeps it approved, so it skips moderation. | Send it back to SUBMITTED. |
| INS7 | Med | `wholesaler_views.py:141-158` | An exception is caught inside `atomic()` after the variants were deleted, causing a partial commit or `TransactionManagementError`. | Validate first, or fail the whole save. |
| INS8 | Med | `distributors/views/profile.py:35,47-50` | The current-password check passes when there is no Laravel user; `bcrypt` raises on legacy hashes; `password_hashing.py` is bypassed. | Use `check_password_hash`. |
| INS9 | Med | `distributors/views/agents.py:19` | `_distributor_laravel_id` falls back to `auth_user.id` (wrong id space, a possible IDOR; UNVERIFIED reachability). | Return None and deny access. |
| INS10 | Med | `wholesaler_views.py:216` | The product toggle runs on GET (CSRF). | Make it POST. |
| INS11 | Med | `rfq_views.py:20`, `public_views.py:189`, `distributors/views/cross_sell.py:65` | Products are fetched without a PUBLISHED filter; the price API is ungated; the variant is not checked against the product. | Filter and gate. |
| INS12 | Med | `wholesale/services/bulk_import_service.py:63-190` | Bulk import runs synchronously, with no size or row cap and about 4 queries per row; an unknown category becomes `first()`. | Cap size and rows, preload lookups, reject unknown categories. |
| INS13 | Med | `rfq_views.py:96`, `rfq_service.py:73` | Quotes are parsed with `float()`, so negative, inf and NaN are accepted. | Use `Decimal` and require > 0. |
| INS14–20 | Low | | The `DIST<id>` invite fallback can be enumerated (6-character minimum password). `str(e)` is leaked in 4 places. `notify_send` and `request_status_change` have no role check. `save_invite_message` creates a `users` row for a superuser. The `auth_bridge` session fallbacks are latent. `innerHTML` XSS in `product_wizard.js:147` and the wholesale categories page. The distributor list loads everything before paginating; the insurance lists are unpaginated. | Small fixes each. |
| INS-S | Struct | | Agent + profile + subscription creation is copied **3×** in `insurance/views/agents.py` (112/325/492), which is why INS1 drifted. The role helpers are duplicated. No tests cover the insurance role matrix, approval guards or wholesale edit. | Use one `insurance_onboarding_service`. |

## 7. Referral Championship + Paldi event

**Done well**
- Admin routes are in the RBAC registry.
- Claims are scoped to the agent and locked.
- Qualification requires `completed` payments and real Razorpay ids.
- The commands are idempotent under locks, and the leaderboard refresh runs `on_commit`.

| # | Sev | Where | Issue | Fix |
|---|---|---|---|---|
| CH1 ✅ | High | `referral_championship/models.py:58-75` | `get_current()` ignores ended or archived campaigns and then creates `slug="championship-2026"` (unique), which raises **IntegrityError** on every campaign page, the dashboard, claims, admin and the registration discount once an admin sets the campaign to ended. | Return the newest campaign; seed only when the table is empty. |
| CH2 ✅ | High | `agents/views/registration.py:3232-3250, 4409-4420` | The 50% campaign price applies whenever the session has `championship_ref_id`, with no `live` or `end_date` check. The campaign ended 2026-10-31 but the discount still works. | Apply it only while live and before `end_date`. |
| CH3 | High | `services/qualification_service.py:147-195` | A refund reverts the referral count but never withdraws claims, so a voucher that is `processing` still gets approved. | Cancel claims above the new count. |
| CH4 | Med | `qualification_service.py:67-71,106-115` | There is no unique `(campaign, referred_agent)` and the lookup runs before the lock, so a referral can be credited twice (UNVERIFIED concurrency). | Add a UniqueConstraint and re-read under the lock. |
| CH5 | Med | `qualification_service.py:171-180` | The revert recount runs without a lock, so updates can be lost. | `select_for_update` the referrer. |
| CH6 ✅ | Med | `views/admin_views.py:292` | "Freeze leaderboard" writes `is_frozen`, which nothing reads. | Skip the refresh when frozen. |
| CH7 | Med | `leaderboard_service.py:28-66` | Blocked cheaters keep their old cached rank. | Delete their cache rows. |
| CH8 | Med | `views/landing.py:38-63,95-98` | An unknown ref shows a random agent; every GET writes a session plus 2 tracking rows. | 404, and dedupe tracking per session. |
| CH9 | Med | `event_referral/views/public_leaderboard.py:48-90` | The public leaderboard runs about 200 queries per hit and always bypasses the cache (auto-reloads every 60 s). It also builds referral lists with mobile and email that are never shown. | Cache the context for 30-60 s and drop the referral entries. |
| CH10 | Med | `attribution_service.py:47-77` | The self-referral mobile check only strips spaces, so `+91…` slips past. | One shared digit normaliser. |
| CH11 | Med | `event_referral/services/qualification_service.py` | A payment for a blocked referrer is dropped before it is marked paid, so it never counts after a restore. | Record it as paid with `counts=False`. |
| CH12–18 | Low | | `_grant_win` puts suspended agents back to `pending_approval`. Admin claim updates have no lock or transition rules. CSV formula injection in the Paldi export. `grant_paldi_trial` commits before the email, so a re-run skips it. N+1 queries in the admin claims and agent dashboard. Every paid referral re-ranks all participants. `whatsapp_templates_json\|safe`. | Small fixes each. |
| CH-S | Struct | | Longest functions: `build_championship_dashboard_json_payload` (339), `admin_trial_activity_logs` (187), `agent_championship_dashboard` (176). The JSON and HTML dashboards duplicate blocks. `registration_link_open_count` is dead. The two apps have separate self-referral checks. | Share one dashboard builder and one attribution helper. |

---

## 8. Cross-cutting themes

1. **Invariant 5 (`|safe` on JSON in `<script>`) is broken in about 12 templates** across agents, home, championship and calculators. `safe_json` already exists. One sweep fixes all of them (WEB1, PAY11, AG6, WEB12, CH18).
2. **Invariant 10 (one activation path) is broken three times:** the WA bot (WA4), the ₹0 checkout (PAY7) and the insurance offline cart (INS1). Each copy has drifted from the shared one.
3. **Invariant 9 (keep every order, check every order) is broken three times:** PAY4, PAY5 and INS1/INS3.
4. **"Mobile = default password"** appears in WA2, PAY1, PAY8, PAY14 and WA8, and the mobile is often shown publicly. Today this is *intended* (CLAUDE.md invariant 3), but it is what makes PAY1 and WA8 dangerous. **Business decision for you:** send a reset or set-password link instead of a default password.
5. **Hidden or suspended agents:** `_hidden_from_public` exists but only the card views use it (AG3).
6. **Unbounded external calls in requests:** Nominatim (WEB3/4), LLM (WA12/AG11), Chromium (AG10), OpenWA in a lock (WA5), Razorpay sleeps (PAY10).
7. **FastAPI ↔ Django drift:** expiry (API6), NULL `expires_at` (API7), social-link keys (API9), UTC vs IST (API13), routing (WEB2).
8. **Giant files:** `registration.py` (6.3K lines), `dashboard.py` (the 975-line `apply_profile_update`), `pages.py` (2.6K lines). The same split pattern used for the admin panel (selectors/services) applies here.

## 9. Roadmap

| Phase | Items | Effort |
|---|---|---|
| **0. Now (takeover / money / prod broken)** | WA1, PAY1, PAY2, PAY3, PAY4, WEB1, AG1, WEB2, CH1, CH2, API1, INS2 | ~1-2 days |
| **1. High** | WA2-5, AG2, AG3, API2, API3, WEB3, WEB4, INS1, CH3, PAY5 | ~2-3 days |
| **2. Invariant sweep** | Every `\|safe` → `safe_json` (theme 1); one activation path (theme 2); one order rule (theme 3); `_hidden_from_public` everywhere | ~2 days |
| **3. Medium bugs / security** | The remaining Med rows (~45) | ~4-5 days |
| **4. Performance** | WEB8/9/11, AG8-11, CH9, API5/12/16, WA13, INS12 | ~3 days |
| **5. Structure + tests** | Split `registration.py`, `dashboard.py` and `pages.py`; merge the duplicated creators; add regression tests for every Phase 0-1 fix plus a routing test | ~1-2 weeks |

Every fix gets a regression test first, and the existing suite (1,223 tests) must stay green. The same "nothing that worked before may break" rule as the admin work applies.
