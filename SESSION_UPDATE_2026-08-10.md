# PadosiAgent Django Port — Session Update

**Date:** 10 Aug 2026
**Scope:** Laravel → Django parity porting (tasks completed in this session)
**Stack:** Django (settings: `padosi_agent.settings`), MySQL/MariaDB, `USE_TZ=False`

---

## 1. What Was Done

### 1.1 Insurance Dashboard — Lead Stats (Completed)
- `src/apps/insurance/views/dashboard.py`
  - Manager dashboard `total_leads` now a real count (`AgentLead` where `agent.insurance_id = current`)
  - Sales dashboard: `recent_leads` (top 5, annotated `agent_name`) and `top_agents` (annotated `leads_count`)
- Replaced hard-coded zero placeholders used by `insurance/dashboard.html`

### 1.2 Insurance Offline Payment — `record_payment` (Completed)
- `src/apps/agents/models.py` — `Agent` gained 4 payment fields: `payment_method`, `payment_reference`, `payment_recorded_at`, `payment_recorded_by` (FK → auth.User)
- Migration: `src/apps/agents/migrations/0016_agent_payment_method_agent_payment_recorded_at_and_more.py`
- `src/apps/insurance/views/payments.py` — new `record_payment` (POST): validation, atomic transaction, status `pending_accounts_payment → pending_admin_approval`, marks subscription completed (+365 days), idempotency, `razorpay_order_id = payment_reference`; `handle_payment_success` persists audit fields
- `src/apps/insurance/views/agents.py` — `checkout_cart` persists offline payment fields; gate: manager/accounts roles only (agents/sales → 403); accounts users allowed in auth check
- `src/apps/insurance/views/dashboard.py` — accounts section filters by `payment_recorded_by = user`
- `src/apps/insurance/templates/insurance/payments/index.html` — modal with **Pay Online / Record Offline** tabs (NEFT/IMPS, Cheque, UPI, Cash; UTR input; date picker)

### 1.3 Distributor Invite Message (Completed)
- `src/apps/distributors/views/dashboard.py` — `save_invite_message` persists to `LaravelUser` (db_table `users`, managed=False): get-or-create by email, role `distributor`, status `active`
- Dashboard read priority: user row → `SiteSetting('distributor_invite_message')` → default; `{LINK}` substituted with referral URL

### 1.4 Check-Pincode Page + API (Completed)
- `src/apps/home/views/pages.py`
  - `check_pincode` — full page with agent-role redirect, `^[1-9]\d{5}$` validation, AJAX partial
  - `check_pincode_agents` — JSON `{success, pincode, count}`, accepts leading zeros
  - `_get_or_create_pincode` — upserts `pincodes` via postalpincode.in (refactored `pincode_fetch` to reuse)
  - `_pincode_matching_agents` — agent_pincode OR service_pincodes JSON (string/int) match
- Templates: `src/templates/check-pincode.html`, `src/templates/partials/pincode-check-results.html` (data-count contract: -1 invalid, 0 exclusive, 1-10 low, >10 established)
- Events register pincode prefill fix (`events.py` `show_form` + `events/register.html`)

### 1.5 Favorites Toggle (Completed)
- **New:** `src/apps/agents/views/favorites.py` — `toggle_favorite` (POST): guest 401 JSON, agent-role 403, invalid/missing agent 400, toggles `FavoriteAgent` row, returns `{status, is_favorited}`
- `src/apps/agents/urls.py` — `agent/toggle-favorite/`
- `favorite_ids` added to `find_agents` (home/views/pages.py) and `agent_dashboard` (agents/views/dashboard.py) contexts
- `src/templates/partials/agent-card.html` — both hearts use `{% if agent.id in favorite_ids %}`
- `src/templates/base.html` — global `toggleFavoriteAgent` JS (guest → quick-register popup / login redirect, AJAX + csrf, Swal errors)

### 1.6 Static Pages (Completed)
- `src/apps/home/views/pages.py` — new views:
  - `marketing` — ports `agentMarketing`: pincode/location/GPS → session (`last_pincode`, `last_location`, `last_lat/lng`, `detected_area`), clean-URL redirect, agent users → `/agent/dashboard/`, `hide_header`
  - `calculator` — agent redirect + render
  - `coming_soon` — plain render
  - `lic_event` — renders with `mobile_stats` / `trust_cards` loop data
  - `cancellation_refund_policy` — plain render
- `src/apps/home/urls.py` — 5 new routes
- Templates created (ported from blade, converted to DTL): `src/templates/public/marketing.html`, `public/calculator.html`, `public/coming-soon.html`, `public/lic-event.html`, `public/cancellation-refund-policy.html`
- Assets: `src/static/lic-branches.json` + `images/curtain-left.png`, `curtain-right.png`, `wooden-floor.png`

### 1.7 Participants + Facebook/Instagram Share Module (Completed)
- **New:** `src/apps/agents/views/participants.py` — ports `ParticipantController` + `FacebookPostController`:
  - `participants_store` — validation (Laravel messages, 422 with `errors` dict), duplicate email/phone checks, `shareable_id = part_<hex>`, JSON products, share URL, 201 response
  - `mark_as_shared` — idempotent (`Already confirmed!`), 404 for unknown
  - `facebook_auto_post` / `facebook_verify_post` / `facebook_store_token` — Graph API v19.0 calls via `requests`, status updates (`connected` / `completed` / `verified`)
  - `facebook_connection_status` — `{connected, facebook_user_id, participant_status, has_posted}`
  - `facebook_confirm_manual_share` — screenshot upload (jpeg/png/jpg, ≤5 MB) to MEDIA_ROOT, post-ID extraction from 4 URL patterns, `manual_share=True`
- `src/apps/agents/urls.py` — 10 new routes (participants + `api/facebook/*`)
- **New:** `src/templates/participants/share.html` — public share card (Facebook/WhatsApp/copy-link)
- `src/templates/public/coming-soon.html` — `X-CSRF-TOKEN` → `X-CSRFToken` headers; fixed `{% csrf_token %}` nested-input bug (now `{{ csrf_token }}` in meta + hidden inputs)

### 1.8 Merge with Concurrent Session Work
- Consolidated duplicate URL blocks and duplicate `participants_router` in `agents/urls.py` / `participants.py`; kept `career_timeline` (`agent/career-timeline/suggestions/`) and `fb_ad_signup` (`join/ad/`) routes intact

---

## 2. All URLs

### 2.1 New/Changed Routes — `src/apps/home/urls.py` (namespace `home`)
| Method | Path | Name | View |
|---|---|---|---|
| GET | `/check-pincode` | `home:check_pincode` | `pages.check_pincode` |
| GET | `/api/pincode/check-agents/<str:pincode>` | `home:check_pincode_agents` | `pages.check_pincode_agents` |
| GET | `/marketing/` | `home:marketing` | `pages.marketing` |
| GET | `/calculator/` | `home:calculator` | `pages.calculator` |
| GET | `/coming-soon/` | `home:coming_soon` | `pages.coming_soon` |
| GET | `/lic-agent/` | `home:lic_event` | `pages.lic_event` |
| GET | `/cancellation-refund-policy/` | `home:cancellation_refund` | `pages.cancellation_refund_policy` |

### 2.2 New Routes — `src/apps/agents/urls.py` (namespace `agents`)
| Method | Path | Name | View |
|---|---|---|---|
| POST | `/agent/toggle-favorite/` | `agents:agent_toggle_favorite` | `favorites.toggle_favorite` |
| GET/POST | `/participants/` | `agents:participants_index` | `participants.participants_router` (GET → index, POST → store) |
| GET | `/participants/create/` | `agents:participants_create` | `participants.participants_create` (→ redirect `/coming-soon/`) |
| GET | `/participants/share/<str:shareable_id>/` | `agents:participants_share` | `participants.participant_share` |
| GET | `/participants/<int:participant_id>/` | `agents:participants_show` | `participants.participant_show` |
| POST | `/participants/<str:shareable_id>/mark-shared/` | `agents:participants_mark_shared` | `participants.mark_as_shared` |
| POST | `/api/facebook/auto-post/` | `agents:facebook_auto_post` | `participants.facebook_auto_post` |
| POST | `/api/facebook/verify-post/` | `agents:facebook_verify_post` | `participants.facebook_verify_post` |
| POST | `/api/facebook/store-token/` | `agents:facebook_store_token` | `participants.facebook_store_token` |
| GET | `/api/facebook/connection-status/<int:participant_id>/` | `agents:facebook_connection_status` | `participants.facebook_connection_status` |
| POST | `/api/facebook/confirm-manual-share/` | `agents:facebook_confirm_manual_share` | `participants.facebook_confirm_manual_share` |

*(Routes added by the concurrent session, kept intact: `join/ad/` → `fb_ad_signup`, `agent/career-timeline/suggestions/` → `career_timeline_suggestions`.)*

---

## 3. Full URL Inventory (New + Existing, for reference)

| Method | Path | App / Namespace |
|---|---|---|
| GET | `/` | home |
| GET | `/about/` `/faq/` `/contact/` `/contact/submit/` | home |
| GET | `/find-agents/` `/find-agents/ai-picks/` | home |
| GET | `/terms/` `/privacy/` | home |
| GET | `/marketing/` `/calculator/` `/coming-soon/` `/lic-agent/` `/cancellation-refund-policy/` | home |
| GET | `/check-pincode` | home |
| GET | `/api/pincode/check-agents/<pincode>` | home |
| GET | `/insurance/api/pincode/fetch/<pincode>` | home |
| GET | `<slug:slug>/` (CMS catch-all) | home |
| GET/POST | `/agent-registration/` `/agent-send-otp/` `/agent-verify-otp/` `/agent-register-step1/` `/agent-register-step2/` `/chooseplan/` `/agent-register-complete/` `/payment-success/` `/payment-failure/` `/agent-registration/success/` `/agent-registration/failed/` `/razorpay-webhook/` `/agent/verify-promo/` | agents |
| GET/POST | `/agent-login/` `/forgot-password/` `/reset-password/<uidb64>/<token>/` `/agent-logout/` `/logout/` | agents |
| GET/POST | `/agent/dashboard/` `/agent/referral/` `/agent/edit-profile/` `/agent/update-profile/` `/agent/push-token/` `/agent/upgrade-plan/` `/agent/referral-info/` `/agent/update-visibility/` | agents |
| GET | `/profile/<slug>/` `/profile/<slug>/review/` `/review/<slug>/` | agents |
| POST | `/agent/leads/capture/` `/agent/leads/update-status/` `/client/quick-register/` | agents |
| GET | `/join/<ref_code>/` `/join/ad/` `/og-image/<id>/preview.jpg` | agents |
| GET | `/auth/google/` `/auth/google/callback/` `/auth/google/get-session-data/` `/auth/google/user-data/` `/auth/google/clear-session/` | agents |
| GET/POST | `/agent/gbp/auth/` `/agent/gbp/callback/` `/agent/gbp/status/` `/agent/gbp/save-url/` | agents |
| POST | `/agent/generate-bio/` | agents |
| POST | `/agent/toggle-favorite/` | agents |
| GET | `/agent/career-timeline/suggestions/` | agents |
| GET/POST | `/participants/` `/participants/create/` `/participants/share/<shareable_id>/` `/participants/<id>/` `/participants/<shareable_id>/mark-shared/` | agents |
| POST | `/api/facebook/auto-post/` `/api/facebook/verify-post/` `/api/facebook/store-token/` `/api/facebook/confirm-manual-share/` | agents |
| GET | `/api/facebook/connection-status/<id>/` | agents |
| GET | `/agent/<slug>/` (public share catch-all) | agents |
| GET | `/events/register` `/events/plans` `/events/payment` `/events/success` | agents (urls_events) |
| GET/POST | `/manifest.webmanifest` `/sw.js` `/offline.html` `/sitemap.xml` | root (PWA) |
| GET | `/insurance-login/` | root |
| GET/POST | `/media/app/private/<path>` `/django-admin/` | root |
| GET/POST | `/chatbot-api/` | chatbot |
| GET/POST | `/admin/...` (admin panel) | admin_panel |
| GET/POST | `/distributor/...` | distributors |
| GET/POST | `/insurance/...` (incl. offline-payment + payments dashboard) | insurance |

---

## 4. Files Touched (This Session)

### New files
- `src/apps/agents/views/favorites.py`
- `src/apps/agents/views/participants.py`
- `src/apps/agents/migrations/0016_agent_payment_method_agent_payment_recorded_at_and_more.py`
- `src/templates/public/marketing.html`
- `src/templates/public/calculator.html`
- `src/templates/public/coming-soon.html`
- `src/templates/public/lic-event.html`
- `src/templates/public/cancellation-refund-policy.html`
- `src/templates/participants/share.html`
- `src/static/lic-branches.json`
- `src/static/images/curtain-left.png`, `curtain-right.png`, `wooden-floor.png`

### Modified files
- `src/apps/agents/models.py` (Agent payment fields)
- `src/apps/agents/urls.py` (favorites, participants, api/facebook routes)
- `src/apps/agents/views/dashboard.py` (favorite_ids, payment audits)
- `src/apps/agents/views/events.py` (pincode prefill)
- `src/apps/home/views/pages.py` (pincode views, favorites context, 5 static-page views)
- `src/apps/home/urls.py` (check-pincode + static page routes)
- `src/apps/insurance/views/payments.py`, `src/apps/insurance/views/agents.py`, `src/apps/insurance/views/dashboard.py`
- `src/apps/insurance/templates/insurance/payments/index.html`
- `src/apps/distributors/views/dashboard.py`
- `src/templates/base.html` (toggleFavoriteAgent JS)
- `src/templates/partials/agent-card.html` (favorite hearts)
- `src/templates/partials/find-agents-list.html` (indirect), `src/templates/public/find-agents.html` (context)
- `src/templates/check-pincode.html`, `src/templates/partials/pincode-check-results.html`
- `src/templates/events/register.html` (pincode prefill)
- `src/templates/public/coming-soon.html` (CSRF header + token fixes)

---

## 5. Verification

- `python src/manage.py check` — clean
- `python src/manage.py makemigrations --check --dry-run` — no changes
- Functional suites: favorites **14/14**, static pages **19/19**, participants/facebook **36/36**
- Live server (PID 7700, `http://127.0.0.1:8000`): all 5 static pages 200; `/participants/` GET 200; POST with real CSRF cookie + `X-CSRFToken` header → **201**
