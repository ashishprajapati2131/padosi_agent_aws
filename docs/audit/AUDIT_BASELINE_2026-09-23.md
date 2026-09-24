# PadosiAgent — Security & Engineering Audit Baseline

| | |
|---|---|
| Audit dates | 2026-09-23 → 2026-09-24 |
| Base commit | `main` @ `f1bbe1a` (clean tree at start) |
| Work branch | `audit/full-remediation-2026-09-23`, committed and pushed as `3408281` (not merged to `main`, not deployed) |
| Scope | Entire repo: Django apps (home, agents, admin_panel, insurance, distributors, chatbot, referral_championship), FastAPI (`/api`), templates/JS, settings, deploy scripts, CI |
| Method | Static code-path tracing of every auth, payment, portal, upload and template-JSON path; baseline test run; targeted fixes + regression tests |
| **Limitation** | No live browser/Lighthouse/pip-audit/bandit run and no MySQL/production instance. The full suite was re-run after the fixes on 2026-09-24: **306 tests, all passing** (§6), including an end-to-end registration → Razorpay (mocked gateway) → dashboard test. |

> This file contains exploit details for issues that are now fixed **and some that are still open**. Keep it out of any public repository.

---

## 1. Executive summary

**Overall condition before the audit: not safe for production.** The platform had several **unauthenticated, single-request account takeovers**:
- A Razorpay callback that logged the caller in as any agent id.
- A public "quick register" endpoint that logged anyone in as any existing user, staff included.
- A sub-distributor portal that authenticated anyone who opened the sub-distributor's public referral link.
- Stored XSS on the public homepage and on the find-agents page.

It also had a way to buy the Starter plan and be activated on Professional or Exclusive, default passwords equal to the account email, and PII leaks.

**All confirmed Critical and High code issues found in this pass are fixed**, except:
- **Registration has no email verification** (`AUD-SEC-018`). This needs a product decision.
- **20,071 people's PAN numbers are committed to git** (`AUD-SEC-019`). This needs owner action.
- **Password == email** (`AUD-SEC-010`) and the extended payment gate (`AUD-SEC-027`) were intentionally left unchanged by owner decision.

**Production readiness: ready with known issues** once a Razorpay **test-mode** smoke test passes and AUD-SEC-019 is handled (§9). The post-fix suite is green (306/306).

## 2. Architecture overview (as actually implemented)

- **Runtime:** GoDaddy cPanel **Passenger WSGI** (`passenger_wsgi.py`). `/api/*` is bridged to the ASGI app via `a2wsgi` (FastAPI on a single shared event loop); everything else goes straight to Django WSGI. `asgi.py` (Daphne/Starlette mount) also exists. Apache sits in front as a local reverse proxy (`REMOTE_ADDR=127.0.0.1`, `X-Forwarded-For` appended).
- **Data:** a single MySQL database is shared by the Django ORM and SQLAlchemy mirror models. Legacy Laravel tables are `managed=False`. There is a file-based cache and `cached_db` sessions.
- **Identities (5):**
  - **Agents:** Django `auth_user` plus the Laravel `users` bcrypt hash. Agent resolution is **by email** in `resolve_agent_for_user()`. CLAUDE.md wrongly said `session['agent_id']`; now corrected.
  - **Admins:** a `session_token` cookie backed by the `user_sessions` table, with `AdminPermissionMiddleware` enforcing deny-by-default staff permissions.
  - **Insurance:** `auth_user` plus an `InsuranceProfile` role.
  - **Distributors:** Laravel `users` (role=distributor), mapped onto a Django user in the `distributor` group.
  - **Sub-distributors:** their own session key.
  - Clients use a passwordless guest identity.
- **Mobile API:** FastAPI with HS256 JWTs whose `jti` must exist in the `user_tokens` table. The signing key is the shared `SECRET_KEY` env var.
- **External services:**
  - Razorpay: orders, signature verification, webhook.
  - Brevo: API email with SMTP fallback.
  - FCM.
  - Google: OAuth login and Business Profile.
  - Facebook Graph.
  - Cloudinary.
  - Groq → Gemini → OpenRouter LLM chain.
  - postalpincode.in and Nominatim.
  - Google Sheets.
  - Playwright IRDAI scraper and AMFI scraper.
- **Background work:** `threading` with `transaction.on_commit` for the invoice PDF and welcome email. There is no Celery or cron in the repo.
- **CI/CD:** GitHub Actions runs `pip install` and `manage.py check`, then SSHes in to run `scripts/deploy_godaddy.sh` (git pull → pip → migrate → collectstatic → Passenger restart). The test suite now runs in CI (non-blocking for now).

## 3. Audit coverage

| Area | Status | Notes |
|---|---|---|
| Agent auth / registration | **FIXED** (1 open) | 6 takeover/PII/brute-force issues fixed; email OTP open (AUD-SEC-018) |
| Payments (Razorpay web, events, insurance, webhook) | **FIXED** | Account takeover, plan escalation, replay, races, promo counter |
| Admin portal | PASS WITH NOTES | Deny-by-default middleware verified; raw SQL parameterised; settings upload hardened; WAF IP spoofing fixed |
| Insurance portal | **FIXED** | Tenant isolation verified PASS; payment reuse, CSRF exemptions, default passwords fixed |
| Distributor / sub-distributor | **FIXED** | Portal auth bypass, fixation, enumeration, brute force |
| Referral championship | PASS WITH NOTES | Tests revived (fixture was broken); logic not re-verified at runtime |
| Chatbot / LLM | **FIXED** | Rate limit was global; cost caps added |
| Public site / templates / JS | **FIXED** | Stored XSS (homepage, find-agents, edit profile), upload XSS |
| FastAPI | **FIXED** | JWT jti, fail-closed key, mass assignment, WAF event-loop blocking, IP spoofing, reset poisoning |
| Database | PASS WITH NOTES | No SQLi found; no unique constraints on Razorpay ids (open); N+1 in sitemap fixed, others noted |
| SEO | PASS WITH NOTES | robots/sitemap/X-Robots-Tag correct; sitemap N+1 fixed. Live-page checks **BLOCKED** (no browser run) |
| Performance | WARNING | Structural fixes only; **no measurements** (blocked) |
| UI/UX & accessibility | **BLOCKED** | Requires browser runs; not performed |
| Deployment / infra | WARNING | Settings hardened; CI runs tests (non-blocking); migrations run automatically on deploy |
| Dependencies | **BLOCKED** | pip-audit/bandit could not run. Note: local env has FastAPI 0.115.6 / SQLAlchemy 2.0.36 vs pinned 0.139 / 2.0.51 |
| Testing | **PASS** | Discovery crash fixed; 32 tests added (27 security regression + 4 registration end-to-end + 1 distributor); full suite 306/306 green |

## 4. Findings

Confidence: **C** = Confirmed by an exact code path; **L** = Likely (depends on proxy/infra behaviour I couldn't observe). All fixes are covered by the passing test suite unless marked otherwise; nothing has been run against production yet.

### Critical

| ID | Component | Finding | Fix |
|---|---|---|---|
| AUD-SEC-001 (C) | `registration.py` `payment_callback` / `_recover_pending_razorpay_checkout` / `_finalize_razorpay_payment` | **Unauthenticated account takeover.** `GET /agent-register/payment-callback/?agent_id=N` logged the caller into any paid agent. `POST /payment-success/` with any completed order id did the same without a signature check. A real ₹1 payment plus `agent_id=<victim>` hijacked the victim. | The agent comes only from the paid order or the server-side `pending_checkout`. Login happens only when the session owns the checkout or the request carries a valid Razorpay signature for that order (`_payer_signature_valid`). The idempotent branch no longer logs in or mutates without one of those. |
| AUD-SEC-002 (C) | Same + `_agent_register_complete_impl`, webhook | **Plan escalation.** The price was computed from `plan_type` while activation trusted the client's `plan_type`/`plan_name`, and the webhook defaulted unknown names to `professional`. So an agent could pay the Starter price and get Professional or Exclusive. | A client plan name is kept only if it resolves to the priced plan. A name resolving to a *different* plan is replaced by the canonical one (`_CANONICAL_PLAN_NAMES`); custom admin names that resolve to nothing are kept as-is. Activation uses `subscription.selected_plan`, falling back to `agent.plan_type` (`_order_plan_slug`), never `professional`. |
| AUD-SEC-003 (C) | `client_quick_register` (csrf_exempt) | **Logged anyone in as any existing user from just an email**, including superusers (who then get `/django-admin/`), agents, insurance and distributors. The mobile-number lookup did the same. | Portal users are never logged in or mutated (`_is_portal_user`). No `auth_user` is created for an agent's email. CSRF is restored, redirects are validated, and new clients get an unusable password instead of `password=email`. |
| AUD-SEC-004 (C/L) | `fb_ad_signup` | Same class of bug: it only blocked agents linked by FK, so staff, insurance, distributors and unlinked agents were logged in. | Same guards as AUD-SEC-003. |
| AUD-SEC-005 (C) | `distributors/views/sub_distributors.py` + `referral_join` | **Sub-distributor portal auth bypass.** The public referral link `/join/<code>/` set `session['sub_distributor_id']`, the exact key the portal used as "logged in". It also had session fixation. | A dedicated `sub_distributor_portal_id` key, set only after a password check or signup, plus `cycle_key()`. |
| AUD-SEC-006 (C) | `home/views/pages.py` + `templates/public/home.html` | **Stored XSS on the homepage.** Anonymous (auto-approved) review text went through `json.dumps` and `|safe` inside `<script>`, then into `innerHTML`. The regex WAF is bypassable (e.g. `onerror =` with a space). | All fields are HTML-escaped at the source, `</` is neutralised, and the avatar URL is URL-encoded. |
| AUD-SEC-007 (C) | `agents/views/dashboard.py` `apply_profile_update`; FastAPI `_sync_login_identity` | **Privilege escalation via email change.** The uniqueness check covered only the `agents` table. An agent could take a staff or insurance `auth_user`'s email; `find_django_user(...).first()` then resolved to the privileged user and the agent's login **overwrote that user's password**. | The email change is rejected if any other `auth_user`/`users` row owns the address (web and API). |

### High

| ID | Component | Finding | Status |
|---|---|---|---|
| AUD-SEC-008 (C) | `GET /participants` | Unauthenticated JSON dump of up to 500 contestants' name, email, phone and insurance details. | FIXED (admin-only) |
| AUD-SEC-009 (C) | Participant Facebook API | Ownership was checked only on a *mismatch*, so with no session or token any participant id was accepted. Anyone could post to a victim's Facebook feed with their stored token. | FIXED (`_owns_participant`) |
| AUD-SEC-010 (C) | `account_auth.create_or_link_django_user`, `post_payment`, insurance onboarding, FastAPI orphan login | **Default password = the account email**, stated in every welcome email. | **NOT CHANGED — owner decision (2026-09-24).** A fix was made and then fully reverted on request. Accepted risk: anyone who knows an agent's email can sign in until that agent changes their password. |
| AUD-SEC-011 (C) | `agent_register_failed` | `?agent_id=N` revealed any agent's name, email and mobile (ids are sequential). | FIXED |
| AUD-SEC-012 (C) | `payment_failure` | A body `agent_id` let anyone move suspended/blacklisted agents to `pending_payment` and fail other agents' orders. | FIXED |
| AUD-SEC-013 (C/L) | `serve_private_file`; media fallback | The ownership check ran on the raw path, so `agents/<me>/../../invoices/<other>.pdf` passed. Also (L) `/media/app//private/…` fell through to `static.serve`. | FIXED (normalise first, `commonpath`; the public media view refuses `app/private`) |
| AUD-SEC-014 (C) | Registration photo (`register_step1/2`) | Anonymous upload of HTML or SVG as a "photo", served same-origin, because model ImageFields don't validate on assignment. | FIXED (format detected from the file bytes with Pillow: JPEG/PNG/GIF/WEBP/BMP, 5 MB max. The stored name gets the matching extension, so `.jfif` and extension-less phone photos still work. Public media served with `CSP: sandbox` + `nosniff`, PDFs exempt) |
| AUD-SEC-015 (C) | `find-agents.html`, `ai_picks_comparison` | Agent-controlled name/city/language interpolated into `innerHTML` (AI picks + compare widget). | FIXED (server-side escaping, JS escaping, names reject `<>`) |
| AUD-SEC-016 (C) | `agents/views/gbp.py` | Reflected XSS via `?error=`; a predictable `state=gbp_<agent_id>` let an attacker attach their Google Business account to any agent's profile; `postMessage('*')`. | FIXED |
| AUD-SEC-017 (C) | FastAPI `profile_service` | Agents could set their own `badge`, `license_number` (the public "IRDAI verified" flag) and an arbitrary `profile_photo_url`, which is fetched server-side with `verify=False` (SSRF). | FIXED (web parity; photo URL restricted to Cloudinary or `/media/`) |
| AUD-SEC-018 (C) | Registration step 1 | **No email verification.** Anyone can overwrite or hijack an *unpaid* registration for someone else's email and squat addresses. Paid and active agents are protected. | **OPEN — needs a product decision:** add an email OTP step (10-min expiry, ≤5 attempts, `compare_digest`, single use). |
| AUD-SEC-019 (C) | Repo root | `blacklisted_agents_insert.sql` and `BlacklistedAgents.xlsx` hold **names and PAN numbers of about 20,071 people**; invoice PDFs are also committed. Not web-served, but exposed to anyone with repo access. | **OPEN — owner action:** confirm the GitHub repo is private, move the data out, and purge it from history (`git filter-repo`), noting DPDP Act obligations. |
| AUD-SEC-020 (C) | `events.py payment_success` | One captured payment could complete other registrations (the order wasn't bound). A concurrent duplicate re-issued the password, invoice and email. | FIXED (a payment id completes only one registration; an order owned by another registration is rejected; a stale order of the same registration is accepted after the amount check) |
| AUD-SEC-021 (C) | `insurance/views/payments.py` | A single online payment could activate several same-priced agents, since the order was not bound to the agent. | FIXED (order `notes.agent_id` check + payment reuse check) |

### Medium

| ID | Finding | Status |
|---|---|---|
| AUD-SEC-022 (L) | `X-Forwarded-For[0]` is client-controlled behind an appending proxy. This enabled rate-limit bypass (agent login, lead capture, FastAPI login/rate limiter) and **auto-blocking of arbitrary IPs** such as an admin's or a shared Jio/Airtel CGNAT address (admin failed-login, WAF). FastAPI `verify_admin_ip` could be bypassed with `XFF: 127.0.0.1` (dead code). | FIXED — right-most public hop (`client_ip_from_forwarded_for`, `fastapi_app/utils/client_ip.py`). **Confirm the proxy chain** (Cloudflare or other CDN?) in production. |
| AUD-SEC-023 | No per-account brute-force limit; distributor and sub-distributor logins had no limit at all. | FIXED (10 failures / 15 min per account + existing per-IP limit) |
| AUD-SEC-024 | Distributor login disclosed any email's role before checking the password; it was `csrf_exempt`; sub-distributor login said "no account found". | FIXED |
| AUD-SEC-025 | Webhook vs browser-callback race (double invoice/email/promo count); `times_used += 1` lost updates bypassed `max_uses`. | FIXED (`select_for_update` + `F()` updates) |
| AUD-SEC-026 | Social-follow discount tiers unlocked with arbitrary platform strings; a GET wrote discount state to any draft id. | FIXED |
| AUD-SEC-027 | Paid-only routes (`/agent/generate-bio/` spends LLM credits, analytics, GBP, QR, career timeline) were reachable by unpaid logged-in agents. | **FIXED** (re-applied at owner request, 2026-09-24): payment gate extended; the AJAX endpoints get a JSON 403 with a redirect hint, pages redirect to `/chooseplan/`. |
| AUD-SEC-028 | Chatbot rate limit was keyed on `REMOTE_ADDR` (the proxy), so it was one global bucket. There was no message cap, a substring origin check, and the Django session key was returned as the chat id. | FIXED |
| AUD-SEC-029 | The FastAPI WAF did synchronous DB work and sent unthrottled alert emails with no timeout inside async middleware, which stalls all `/api` traffic under a payload flood. | FIXED (thread pool, 1 email / IP / 10 min, timeout, escaping) |
| AUD-SEC-030 | JWTs without `jti` skipped the revocation registry; the signing key fell back to a value committed in `config.py`. | FIXED (jti required; the app refuses to start in prod with an empty or committed key, and asgi then serves Django-only) |
| AUD-SEC-031 | Anonymous review **overwrite** by reviewer email. | FIXED. **OPEN:** fake-review inflation (auto-approved, unverified, drives feature unlocks) — needs a verification or moderation decision. |
| AUD-SEC-032 | Google login OAuth had a constant `state` and no HTTP timeouts. | FIXED |
| AUD-SEC-033 | Reset links lasted 3 days (the email says 60 min); the staff-account message enabled enumeration; a password reset flipped a distributor's `users.role` to `agent`. | FIXED |
| AUD-SEC-034 | Admin settings upload accepted any field and extension (HTML/SVG → same-origin XSS by staff); `update_settings` wrote any posted key into `SiteSetting`, including `pricing_config`. | FIXED (upload hardening + per-group allow-list `SETTINGS_FORM_KEYS` matching exactly the General/SEO/Security form fields). |
| AUD-SEC-035 (L) | FastAPI reset link built from `Host`/`X-Forwarded-Host` (reset poisoning); reset didn't revoke existing API tokens. | FIXED |
| AUD-SEC-036 | `edit_profile.html`: a Python dict `repr` rendered with `|safe` in `<script>` (agent→admin XSS; `None` breaks JS). | FIXED (`safe_json` filter) |
| AUD-SEC-037 | The public OG image endpoint's `?nocache=1` forced a PIL render per request. | FIXED (owner/admin only) |
| AUD-SEC-038 | With the `CSRF_TRUSTED_ORIGINS` env var unset, production trusted `https://*.ngrok-free.dev` and localhost origins. | FIXED |
| AUD-SEC-039 | Insurance cart/checkout endpoints were `csrf_exempt`; insurance-onboarded agents were created with `password=email`. | FIXED |
| AUD-SEC-040 | Welcome email interpolated unescaped names; FastAPI Jinja environment without autoescape. | FIXED |
| AUD-REL-041 (C, found by the first real test run 2026-09-24) | **Payment activation could silently roll back.** Best-effort steps (referral code insert, referral credit, championship hook, promo count, activity log) ran inside the activation `transaction.atomic()` behind bare `try/except`. Any DB error there marked the whole transaction for rollback, so the subscription stayed `pending` while the user saw "success". Trigger seen in tests: `ReferralCode.generateForAgent` inserted `created_at = NULL`. | FIXED: each step runs in its own savepoint (`_isolated()` helper, shared by all 4 activation paths); `RegistrationActivityLog.log` uses its own savepoint; `generateForAgent` now sets `created_at`/`updated_at`. |

### Low / informational

Fixed on 2026-09-24:
- **Auto-block expiry.** Automatic WAF and brute-force IP blocks (reason starting "Auto-blocked") now expire after 24 hours in both Django (`is_ip_blocked`) and FastAPI; manual admin blocks stay permanent. The regex false-positive risk itself remains.
- **Cross-site logout.** A cross-site GET logout (`Sec-Fetch-Site: cross-site`) is ignored; normal logout links work unchanged.
- **Refunds.** Full refunds (`refund.processed` webhook) mark the subscription and invoice `refunded`, set the agent to `pending_payment` if no other real payment remains, and revert championship credit. Partial refunds are ignored. **Enable the `refund.processed` event in the Razorpay dashboard webhook settings.**
- **Callback sleeps.** `payment_callback` retries and sleeps only for genuine payers (valid signature or own pending checkout).
- **Page CSP.** HTML pages now get a minimal CSP (`base-uri 'self'; object-src 'none'`) that doesn't restrict scripts, styles or CDNs.
- **Admin sessions.** New admin logins last 7 days (was 30); existing sessions keep their expiry.
- **CI.** CI now runs the test suite (non-blocking; remove `continue-on-error` once green).
- **Distributor dashboard 500 (found by the new distributor test).** A distributor without a referral code got an error on their first dashboard visit: `get_or_create` inserted `referral_codes.created_at = NULL`, the same Laravel-table bug as AUD-REL-041. The timestamps are now set.
- **Distributor N+1 queries.** Per-sub-distributor agent counts are one grouped query (`sub_distributor_agent_counts`) on the distributor dashboard, the sub-distributor index and the sub-distributor agents page. The 6-month trend is one query. On the distributor agents list, draft sub-distributors are loaded in one query and the active plan per row is preloaded (`page_active_sub`, same rule as `Agent.activeSubscription`); `subscriptions` are prefetched on the sub-distributor agents page.
- **CMS HTML.** Admin-authored HTML (CMS pages, About, agent-dashboard coming-soon box, hero heading, plan feature names, event plan icons and urgency line) now renders through `|clean_html` (`apps/home/html_sanitizer.py`) instead of `|safe`/`autoescape off`. Formatting, classes, inline styles, `<style>` blocks, SVG icons, images, iframes and links are kept. `<script>`, event handlers, `javascript:`/`data:` URLs (except inline `data:image/` images), comments and similar are removed. Plain-text values render byte-for-byte as before. Normal CMS pages are edited in CKEditor, which never kept `<script>`, so no working embed was lost.
- **Raw HTML CMS pages** (`is_raw_code`) are served as-is on the main origin and are **unchanged**: existing pages, scripts included, render byte-for-byte as before. New rule: only a **Super Admin** can add or change raw content that contains scripts, event handlers or `javascript:` URLs (`raw_script_save_blocked`, detection `has_active_content`). Staff can still save script-free raw HTML, and can still edit title/SEO/status of an existing script page as long as its content is unchanged. The admin **Live Preview** iframe no longer has `allow-same-origin` and uses `srcdoc`, so previewed scripts still run but can't reach the admin panel or its session.

Not changed:
- **No DB unique constraint on Razorpay ids, intentionally.** The insurance bulk-cart checkout legitimately stores one payment id/reference for every agent in the cart, so a unique index would break bulk onboarding. Replay protection stays in code.
- The insurance offline "payment reference" is stored in `razorpay_order_id`.
- The Django visibility toggle lacks the FastAPI feature-lock checks.
- `is_distributor()` is true for superusers (by design).
- FastAPI `send_welcome_email` is dead code and references a template path that doesn't exist.

### Test-infrastructure findings

- **AUD-TST-001 (FIXED):** `apps/home/tests.py` and the `apps/home/tests/` package collided, so `manage.py test apps` crashed at discovery. The module was moved to `apps/home/tests/test_pages.py`.
- **AUD-TST-002:** 9 pre-existing failures/errors.
  - 5 championship errors came from a fixture using non-existent `Agent.city/state`. **Fixture fixed.**
  - `review_threshold_just_crossed(1,5)` asserted the opposite of the function's documented contract. **Assertion corrected.**
  - The QR profile URL test was stale after the switch to canonical state-prefixed URLs. **Updated.**
  - `test_profile_focus_reviews_renders_scroll_hook` and `test_resolve_plan_adds_unlocks_without_visibility` expected review unlocks to override the admin plan lock. Production behaviour (admin lock wins) was kept and the tests were updated to it, with added positive and negative cases. **Resolved.**
- **AUD-TST-003 (test environment only):** the legacy `favorite_agents` table is created without its `user_id`/`agent_id` columns in the test DB, because the migration state lacks the FKs. The full dashboard page can't render in tests without stubbing that one lookup. Production MySQL is unaffected.
- **AUD-TST-004 (pre-existing drift):** `makemigrations --check` reports a pending `AlterField` on `AgentCardImpression.agent` that predates this audit. It's harmless because deploy runs only `migrate`; generate and review it separately.

### Registration re-check (2026-09-24)

The full agent-registration flow was re-verified with a new end-to-end test: step 1, step 2, plan, order, payment verify or redirect callback, auto-login, dashboard. It also covers unpaid agents going to `/chooseplan/` and the temp password being the email. Regressions from this audit's own fixes, found and fixed:
- Photo validation rejected real `.jfif` and extension-less photos. It now detects the format from the file content.
- Events payment rejected a genuinely paid stale-tab order of the same registration.
- Custom admin plan display names were rewritten to the canonical name on the subscription and invoice. They are now kept.
- The QR review page showed the duplicate-review error as raw JSON. The response now carries `message`.

## 5. Changes made (files)

| File | Why |
|---|---|
| `apps/agents/views/registration.py` | AUD-SEC-001/002/003/004/011/012/014/025/026, name validation |
| `apps/agents/views/events.py` | AUD-SEC-020/025 |
| `apps/agents/views/auth.py` | AUD-SEC-022/023/032/033 |
| `apps/agents/views/dashboard.py` | AUD-SEC-007/013/022/031/037, name validation |
| `apps/agents/views/participants.py` | AUD-SEC-008/009 |
| `apps/agents/views/gbp.py` | AUD-SEC-016 |
| `apps/agents/services/account_auth.py` | AUD-SEC-010 (`welcome_email_password`, unusable default) |
| `apps/agents/services/post_payment.py`, `services/brevo.py` | AUD-SEC-010/040 |
| `apps/agents/middleware.py` | AUD-SEC-027 |
| `apps/admin_panel/middleware.py`, `views/dashboard.py`, `views/settings.py`, `views/insurance_approvals.py` | AUD-SEC-022/034/010 |
| `apps/insurance/views/payments.py`, `views/agents.py` | AUD-SEC-021/039 |
| `apps/distributors/views/auth.py`, `views/sub_distributors.py` | AUD-SEC-005/023/024 |
| `apps/chatbot/views.py` | AUD-SEC-028 |
| `apps/home/views/pages.py`, `templatetags/json_tags.py` (new) | AUD-SEC-006/015/036 |
| `templates/public/find-agents.html`, `templates/agents/edit_profile.html` | AUD-SEC-015/036 |
| `padosi_agent/settings.py`, `urls.py`, `sitemaps.py` | AUD-SEC-033/038/013/014, sitemap N+1 |
| `fastapi_app/config.py`, `dependencies/auth.py`, `dependencies/ip_whitelist.py`, `middleware/threat_monitor.py` (rewritten), `middleware/rate_limiter.py`, `utils/client_ip.py` (new), `services/auth_service.py`, `services/profile_service.py`, `services/password_reset_service.py`, `services/email_service.py` | AUD-SEC-010/017/022/029/030/035/040 |
| Tests: `apps/agents/test_audit_security.py` (new, 27 tests), `apps/agents/test_registration_e2e.py` (new, 4 tests), `apps/distributors/tests.py`, `apps/agents/test_qr_review_growth.py`, `apps/referral_championship/tests.py`, `apps/home/tests/test_pages.py` (moved) | Regression coverage / stale fixtures |
| `CLAUDE.md` | Corrected the agent-identity claim; added **Security invariants** |

### Behaviour changes to QA before release

*Revised 2026-09-24 per owner:*
- The welcome email and temp password are unchanged (still the email).
- Unpaid agents are now redirected to the plan page from bio generator, QR, GBP, analytics and career timeline (the AJAX calls return a JSON "please complete payment" message).
- New admin logins last 7 days.
- Full refunds remove access.
- Existing sub-distributor sessions keep working with no re-login.
- A payer landing in a different browser with a valid Razorpay signature is still auto-logged in.

Remaining visible changes:
1. Anonymous reviews can't be edited later (a duplicate email returns 422).
2. Quick-register with an agent, staff or other portal email records the lead but doesn't sign in.
3. Agent names containing `<` or `>` are rejected. Registration photos must be real images ≤5 MB.
4. Mobile API: `badge` and `license_number` are ignored on agent updates; `profile_photo_url` must be Cloudinary or `/media/`.
9. The mobile API **refuses to start in production** if `SECRET_KEY` is empty or equals the old committed value; Django keeps serving and `/api` returns 404.
10. Chatbot messages over 2,000 characters are rejected. Login throttle: 10 failures per 15 minutes per account.
11. `GET /participants` is admin-only.

## 6. Test results

| Run | Result |
|---|---|
| Baseline `manage.py test apps` | **Crashed at discovery** (AUD-TST-001) |
| Baseline after the module move, `manage.py test apps fastapi_app` | **271 run — 4 failures, 5 errors** (listed in AUD-TST-002) |
| `manage.py check` / `check --deploy` (DEBUG=False, dummy secret) | 0 issues (before fixes) |
| Post-fix, first run (2026-09-24) | 298 run: 3 failures (1 real bug, AUD-REL-041; 2 stale tests) |
| Post-fix, after the AUD-REL-041 fix | 298 run: 2 failures (stale tests, AUD-TST-002) |
| **Post-fix final** `manage.py test apps fastapi_app` | **306 run, all passing** |
| `manage.py check` (post-fix) | 0 issues |
| Browser / Lighthouse / pip-audit / bandit | **NOT RUN** |

## 7. Performance before vs after

No performance measurements were taken, so **no numbers are claimed**. Structural changes that should help:
- FastAPI WAF DB and email work moved off the shared event loop.
- Sitemap agent query changed from N+1 to a single join.
- Chatbot per-client limits and a message cap.
- OG-image cache bypass restricted.

## 8. Security status (remaining confirmed risks)

1. **AUD-SEC-018:** no email verification at registration (unpaid-registration hijack and email squatting).
2. **AUD-SEC-019:** PAN/PII data committed to git.
3. **Email-as-password (accepted by owner):** any agent who hasn't changed their temporary password can be logged into by anyone who knows their email.
4. **Fake reviews:** auto-approved anonymous reviews drive feature unlocks.
5. **Proxy topology unverified** for the IP logic (AUD-SEC-022).
6. **No production verification yet:** fixes are covered by tests (Razorpay gateway mocked), not by a live run.

## 9. Production readiness

**Not ready** until:
- (a) ~~the full test suite passes on this branch~~ (done: 306/306);
- (b) a Razorpay **test-mode** end-to-end run covers new registration, upgrade, the netbanking callback, the webhook, the free trial and the event registration;
- (c) `SECRET_KEY` and `CSRF_TRUSTED_ORIGINS` are confirmed in the production `.env`;
- (d) AUD-SEC-019 is handled.

After that: **ready with known issues** (AUD-SEC-018, fake reviews, accepted email-as-password, the Low list).

## 10. Remaining technical debt (intentionally not changed)

- `registration.py` (~4k lines) and `dashboard.py` (~2.7k lines) mix views, payment logic and pricing. The best-effort activation steps are now shared helpers (`_isolated`, `_credit_referral_conversion`, etc.); a proper `payments` service is still worth extracting.
- There are three payment-activation implementations with drift (`_finalize_razorpay_payment`, `verify_and_activate_pending_payment`, webhook); unify them.
- Background work uses bare threads (lost on worker restart), and there is no job queue.
- The WAF is regex-based with permanent IP blocks.
- The CI test step is non-blocking (`continue-on-error: true`). Remove that once one CI run on GitHub is green, so a failing suite stops the deploy.
- The deploy runs `migrate` automatically with no backup step.

## 11. Audit baseline

- **Commit/version:** base `f1bbe1a` on `main`; fixes on branch `audit/full-remediation-2026-09-23` (`3408281`, pushed; the re-check follow-ups are not yet committed).
- **Dependencies checked (by reading, not scanning):** Django 5.2.16, FastAPI 0.139.0 (local 0.115.6), SQLAlchemy 2.0.51 (local 2.0.36), python-jose 3.5.0, razorpay 2.0.1, bcrypt 3.2.2, pillow 12.3.0. `jinja2`, `cloudinary` and `openai` are **unpinned** in `requirements.txt`.
- **Tests at baseline:** 271 (4F/5E). Now: 306, all passing. Added: 27 in `test_audit_security.py`, 4 in `test_registration_e2e.py`, 1 distributor regression test.
- **Invariants to hold:** the "Security invariants" section in `CLAUDE.md`.
- **First commands for the next engineer:**
  ```bash
  python manage.py test apps fastapi_app --noinput
  python manage.py check --deploy
  python -m pytest test_forensic_fixes.py fastapi_app/test_hybrid_fixes.py
  ```
- **Known external limitations:** no access to a production database, the proxy config or the live site during this audit.
