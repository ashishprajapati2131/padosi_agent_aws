# Schema

Alembic is the schema source of truth:

`backend/alembic/versions/0001_initial_schema.py` (revision `0001_initial`).

This note describes the tables. Do not keep a second DDL file that can drift from the migration.

## Tables

- `users` — id, email (unique index `ix_users_email`), password_hash, role (`admin` or `user`), is_active, created_at
- `searches` — id, user_id, query, category, location_text, formatted_address, latitude, longitude, radius_meters, keyword, language, search_mode, filters_json, field_mode, result_count, status, error_message, created_at
- `places` — id, google_place_id (unique), dedupe_key, name, address, latitude, longitude, rating, review_count, phone, website, business_status, maps_uri, types_json, opening_hours_json, raw_allowed_json, created_at, updated_at
- `search_results` — id, search_id, place_id, distance_meters, position, created_at, unique (`search_id`, `place_id`)
- `saved_places` — id, user_id, place_id, created_at, unique (`user_id`, `place_id`)
- `exports` — id, user_id, search_id (nullable), format, field_mode, row_count, created_at
- `api_usage` — id, user_id (nullable), endpoint, search_type, google_operation, success, status_code, duration_ms, result_count, error_type, created_at

`places.dedupe_key` is an internal key used when Google does not return a place id. It is not an export column.

## Retention

`SEARCH_RETENTION_DAYS` defaults to 90. `cleanup_expired()` in `backend/app/services/retention.py` deletes searches, their results, and their export rows older than that cutoff, then deletes place rows that are neither saved nor still referenced by a search result.

Saved places are kept. There is no cron in this app. Call `POST /api/admin/retention/cleanup` and schedule that call in production. Retention must follow the current Google Maps Platform terms. If those terms limit caching to a shorter period than 90 days, lower `SEARCH_RETENTION_DAYS`.

Apply the schema with:

```bash
cd backend
alembic upgrade head
```
