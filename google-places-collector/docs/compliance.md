# Compliance

This app searches through the official Google Places API (New) and Geocoding API. It does not scrape Google Maps HTML, drive the Maps UI with a browser, bypass CAPTCHA, quotas, or rate limits, harvest reviews, or use fake accounts.

## What the product claims

The interface says "Search places matching your query." A result count is the number of matches returned for that search after the server cap, deduplication, and filters. It is not every business in a city and it is not the contents of Google Maps.

The dashboard shows this disclaimer:

> Google Places data is provided through Google Maps Platform. Availability, fields, usage limits, and storage/export permissions are subject to Google's current terms and API policies.

Missing fields are shown as "Data not available". The app does not invent them.

## Storage

`backend/app/services/storage_policy.py` is the list of fields the app will persist. Place IDs stay on, because they are the deduplication key and Google permits storing place IDs. Review text, photos, and other fields that are not on that list are not stored.

Turn a stored field off without a code change:

```bash
STORAGE_DISABLED_FIELDS=latitude,longitude
```

`places.raw_allowed_json` holds only the normalized fields the storage policy kept. It is not a copy of the Google response.

## Export

`backend/app/services/export_fields.py` is a separate allowlist: name, address, phone, website, rating, review_count, place_id, latitude, longitude, business_status, maps_uri. Each one can be disabled:

```bash
EXPORT_DISABLED_FIELDS=latitude,longitude
EXPORT_FIELD_FLAGS={"phone": false}
```

A disabled field is absent from CSV and XLSX. A field that was not stored is also absent. The default list is conservative and policy-adjustable. Review it when the Maps Platform terms change.

## Retention

`SEARCH_RETENTION_DAYS` defaults to 90. Google often limits how long you may cache content other than place IDs (commonly 30 days). If the current terms are shorter than 90 days, lower this setting. Cleanup is `POST /api/admin/retention/cleanup`. This repository does not ship a cron job. Schedule that endpoint in production. Places that a user has saved are not deleted.

## Keys and logs

The server key stays in `GOOGLE_MAPS_API_KEY` on the API process. The React app may receive only `VITE_GOOGLE_MAPS_BROWSER_KEY`, and only for the Maps JavaScript API. Logs record the operation, field mode, status, count, and duration. They do not record the key, request URLs that contain a key, database credentials, or server paths. Clients receive a short message, not a stack trace.
