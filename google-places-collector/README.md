# Google Places Data Collector

A small SaaS for searching places through the official Google Places API (New). You type any category and any location. The same flow covers a hotel in Ahmedabad, a school, a petrol pump with a pincode, or a gym in Navrangpura. Categories are not hard-coded.

The screen says "Search places matching your query." A result count is the size of that search. It is not every business in a city and it is not a copy of Google Maps.

## Architecture

```
React (Vite) → FastAPI → Search Service → GooglePlacesProvider → Google Places API (New)
                                      ↘ Geocoding API
```

The browser talks only to this API. `GOOGLE_MAPS_API_KEY` stays on the server. An optional `VITE_GOOGLE_MAPS_BROWSER_KEY` may load the Maps JavaScript API. If that key is empty, the map is hidden and the table still works.

`PlaceProvider` is the seam for a future source. `GooglePlacesProvider` is the only implementation, selected by `PLACE_PROVIDER=google`.

## Install

Requirements: Python 3.11+, Node 20+, and PostgreSQL for production. Docker Compose is the production path. Tests use SQLite and do not call Google.

```bash
cd google-places-collector
cp .env.example .env
```

Set `JWT_SECRET` to a long random value. Set `GOOGLE_MAPS_API_KEY` only when you are ready to call Google. See [docs/google-cloud-setup.md](docs/google-cloud-setup.md).

### API

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

For a laptop without Postgres, set in `.env`:

```bash
DATABASE_URL=sqlite:///./places_dev.db
```

Compose already points `DATABASE_URL` at the `postgres` service.

```bash
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Web

```bash
cd frontend
npm install
npm run dev
```

Vite reads the collector `.env` and exposes only `VITE_` variables. Open http://localhost:5173.

If `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set and that email does not exist yet, the API creates the admin on startup. It never overwrites an existing password, and no password is hard-coded.

## Environment

| Variable | Purpose |
|---|---|
| `GOOGLE_MAPS_API_KEY` | Server key. Places API (New) and Geocoding only. |
| `GOOGLE_PLACES_FIELD_MODE` | `minimal`, `standard` (default), or `detailed`. |
| `DATABASE_URL` | SQLAlchemy URL. Compose uses Postgres. |
| `JWT_SECRET` | Required in production. |
| `JWT_ACCESS_MINUTES` | Access token lifetime. Default 30. |
| `JWT_REFRESH_DAYS` | Refresh token lifetime. Default 7. |
| `MAX_RESULTS_PER_SEARCH` | Hard cap. Default 100. |
| `MAX_SEARCHES_PER_MINUTE` | Per user. Default 10. |
| `MAX_SEARCHES_PER_MINUTE_IP` | Per client address. Default 20. |
| `GOOGLE_API_TIMEOUT` | Seconds. Default 10. |
| `GOOGLE_API_MAX_RETRIES` | Retries for 429/500/503/timeouts only. Default 2. |
| `SEARCH_RETENTION_DAYS` | Default 90. Must follow current Google terms. |
| `BULK_MAX_ROWS` | Default 25. |
| `BULK_CONCURRENCY` | Default 1. Capped at 3. |
| `LOG_LEVEL` | Default `INFO`. |
| `ENVIRONMENT` | `development` or `production`. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Optional first admin. |
| `CORS_ORIGINS` | Default `http://localhost:5173`. |
| `VITE_API_URL` | Dev API origin. Empty in the Compose build so the UI calls same-origin `/api`. |
| `VITE_GOOGLE_MAPS_BROWSER_KEY` | Optional Maps JavaScript key. |
| `STORAGE_DISABLED_FIELDS` | Optional comma list. See compliance. |
| `EXPORT_DISABLED_FIELDS` / `EXPORT_FIELD_FLAGS` | Optional export switches. |

## Production

```bash
docker compose up --build
```

Postgres, the API (Alembic `upgrade head` on start), and nginx on port 5173. The UI proxies `/api` to the API. Bulk searches can run for a few minutes. nginx `proxy_read_timeout` is 300 seconds.

Behind this proxy the API sees the frontend container address, not the browser, because it does not trust `X-Forwarded-For`. Per-IP limits are per process and per direct client. Put a trusted proxy in front and teach the app that hop before you rely on IP limits in production.

## API

See [docs/api.md](docs/api.md). Short list:

- `POST /api/auth/register` `POST /api/auth/login` `POST /api/auth/refresh` `GET /api/auth/me`
- `POST /api/search` `GET /api/search/{id}` `POST /api/search/{id}/rerun` `POST /api/bulk-search`
- `GET /api/places/{id}` `GET|POST /api/saved-places` `DELETE /api/saved-places/{id}`
- `GET /api/history` `DELETE /api/history/{id}`
- `POST /api/exports` `GET /api/exports` `GET /api/exports/{id}`
- `GET /api/settings` `GET /api/health`
- `GET /api/admin/stats` `GET /api/admin/api-usage` `POST /api/admin/retention/cleanup`

## Cost and terms

Field masks, a hard result cap, and no map tiling are the cost controls. Details are in [docs/cost-control.md](docs/cost-control.md). Storage and export lists are configurable. Read [docs/compliance.md](docs/compliance.md) before you keep data.

## Troubleshooting

- "Google Maps API key is not configured on the server." — `GOOGLE_MAPS_API_KEY` is empty. The UI can still load.
- "A browser key is not configured." — the map is off. The table does not need that key.
- Location not found — Geocoding returned no result. Try a broader place name.
- Quota or billing errors stop a bulk batch. Fix the Cloud project before retrying.
- Nearby search sends the category as a generic type token, not a built-in list. Free text such as "Petrol Pump" belongs in text mode unless it is a valid Places type.
- `alembic upgrade head` from `backend/` applies `0001_initial`.

## Verification run for this tree

Commands that were run while building this app:

- `npm run lint` in `frontend/` — passed
- `npm run build` (`tsc -b && vite build`) — passed
- `ruff check app tests` in `backend/` — passed
- `pytest` — passed, with Google HTTP mocked
- `alembic upgrade head` and `alembic check` against SQLite — passed
- Frontend source and `dist/` were searched for `GOOGLE_MAPS_API_KEY` and `AIza` — no matches
- A local UI pass (register, dashboard, search form, settings, history) against the API with no Google key showed the disclaimer and the message "Google Maps API key is not configured on the server."
- Docker was not installed in the build environment, so Postgres via Compose was not started
- `GOOGLE_MAPS_API_KEY` was unset, so no live Google search was run

## Known limits

- Text Search page size is at most 20. `nextPageToken` must be in the field mask or Google drops it.
- Nearby Search here is a single page of at most 20 results.
- The API can return fewer places than the cap. That is not complete coverage.
- `regularOpeningHours` is requested only in detailed mode.
- The in-memory rate limiter is per process.
- Retention cleanup is an admin call, not a cron job.
- Default retention is 90 days. Current Google terms may require a shorter cache. Lower `SEARCH_RETENTION_DAYS`.
- Prices change. Confirm current SKUs before production billing.
