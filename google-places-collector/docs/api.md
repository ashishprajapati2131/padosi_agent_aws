# API

Base path: `/api`. Authenticated routes expect `Authorization: Bearer <access_token>`.

Errors are JSON: `{ "detail": "...", "error_type": "..." }`. Search failures may also include `search_id`. The client message does not include keys, stack traces, or server paths.

## Health

`GET /api/health` — `{ status, service, google_configured }`. Does not call Google.

## Auth

- `POST /api/auth/register` — `{ email, password }` (password at least 8 characters). Returns access token, refresh token, and user. `409` if the email exists.
- `POST /api/auth/login` — `{ email, password }`.
- `POST /api/auth/refresh` — `{ refresh_token }`.
- `GET /api/auth/me` — current user.

Roles are `user` and `admin`. Admin routes return `403` with "Admin access is required."

If `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set at startup and no user with that email exists, the API creates that admin. It does not reset an existing password. There is no hard-coded password.

## Settings

`GET /api/settings` — signed-in users. Returns field mode, retention days, max results, per-minute search limit, bulk limits, and environment. No secrets.

## Search

`POST /api/search`

```json
{
  "category": "Hotel",
  "location": "Ahmedabad",
  "radius_km": 5,
  "keyword": null,
  "max_results": 20,
  "language": "en",
  "search_mode": "text",
  "min_rating": null,
  "min_reviews": null,
  "has_website": false,
  "has_phone": false,
  "has_both": false
}
```

`search_mode` is `text` or `nearby`. The user sends a location string, not coordinates. The response includes `search`, `results`, `page`, `page_size`, `total`, and `message`. Zero matches are HTTP 200 with "No places found for this search."

`GET /api/search/{id}` — owner or admin. Query: `page`, `page_size`, `sort`, `min_rating`, `min_reviews`, `business_status`, `type_contains`, `q`, `has_website`, `has_phone`, `has_both`, `max_distance_km`.

Sort values: `position_asc` (stored order, not a Google ranking), `rating_desc`, `rating_asc`, `reviews_desc`, `name_asc`, `name_desc`, `distance_asc`.

`POST /api/search/{id}/rerun` — runs the same query again and stores a new search.

`POST /api/bulk-search` — `{ csv_text, confirm }` or `{ rows, confirm }`. CSV header `category,location,radius`. `confirm: false` returns the count and the message "You are about to perform N searches." and does not call Google. `confirm: true` runs the rows. More than `BULK_MAX_ROWS` is rejected. Quota, billing, and auth errors stop the batch. The response includes `stopped`, `stop_reason`, `failed_row`, and per-row `results`.

Search endpoints return `429` when the per-user or per-IP limit is exceeded.

## Places

- `GET /api/places/{id}` — a place from the caller's searches or saved list, or any place for an admin. May refresh from Place Details. On a Google error the stored row is returned with `detail_warning`.
- `GET /api/saved-places`
- `POST /api/saved-places` — `{ place_ids: [1, 2] }`
- `DELETE /api/saved-places/{saved_id}`

## History

- `GET /api/history?page=1&page_size=20`
- `DELETE /api/history/{id}` — owner only.

## Exports

- `POST /api/exports` — `{ search_id, format: "csv"|"xlsx", place_ids? }` or `{ saved: true, format, place_ids? }`. Response is the file. Columns come from the export allowlist.
- `GET /api/exports`
- `GET /api/exports/{id}` — rebuild and download.

## Admin

- `GET /api/admin/stats` — users, searches, searches today, API request count, API error count, `estimated_google_requests` (the same outbound call count), top categories, top locations, recent searches, failed requests.
- `GET /api/admin/api-usage?days=30` — daily searches, daily errors, categories, locations.
- `POST /api/admin/retention/cleanup` — runs retention. Schedule this in production. There is no built-in cron.
