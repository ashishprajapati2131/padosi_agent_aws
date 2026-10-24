# Cost control

Prices change. Check the current [Google Maps Platform pricing](https://developers.google.com/maps/billing-and-pricing/pricing) and the Places API (New) SKU list before you rely on a cost estimate. This app records **request counts**, not dollars.

## What is billed

Each of these is a separate outbound call:

- Geocoding, once per search, to turn the location string into a point.
- Places Text Search, once per page. Page size is at most 20. A search that follows pages can be several Text Search SKUs.
- Places Nearby Search, one call. The current Nearby Search (New) request used here does not paginate and `maxResultCount` is at most 20.
- Place Details, when a user opens a place and a Google place id is stored. Details uses the detailed field mask.

## Why field masks matter

The `X-Goog-FieldMask` header selects both the fields and, on Places API (New), the SKU. The app never requests every field.

`GOOGLE_PLACES_FIELD_MODE`:

| Mode | Search mask |
|---|---|
| minimal | id, displayName, location, formattedAddress, types |
| standard (default) | minimal plus phones, websiteUri, rating, userRatingCount, businessStatus, googleMapsUri |
| detailed | standard plus regularOpeningHours |

Text Search also requests `nextPageToken`. Without it, Google omits the token and pagination cannot continue. Nearby Search and Place Details do not request `nextPageToken`. `regularOpeningHours` is requested only in detailed mode because it is a higher SKU and is not needed for the list.

## Caps in this app

- `MAX_RESULTS_PER_SEARCH` (default 100) is a hard cap. The client cannot raise it.
- Pagination stops at that cap, on an empty page, when the next token repeats, or when Nearby Search returns its single page.
- There is no grid or circle tiling.
- `MAX_SEARCHES_PER_MINUTE` (default 10 per user) and `MAX_SEARCHES_PER_MINUTE_IP` (default 20). Bulk search reserves the whole batch first and returns 429 if it would exceed the limit.
- `BULK_MAX_ROWS` (default 25) and `BULK_CONCURRENCY` (default 1, hard ceiling 3). A quota, billing, or auth error stops the rest of the batch.
- Place details has its own per-user limit (`MAX_DETAIL_REQUESTS_PER_MINUTE`, default 60).
- `GOOGLE_API_MAX_RETRIES` (default 2) retries only HTTP 429, 500, 503, and timeouts. It does not retry 400, 401, 403, billing errors, or an invalid key.
- `GOOGLE_API_TIMEOUT` (default 10 seconds).

The admin screen labels outbound Google calls as request counts. It does not show a price.
