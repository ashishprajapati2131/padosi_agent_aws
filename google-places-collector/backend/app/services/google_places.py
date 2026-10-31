"""The only module that calls the Places API (New) over HTTP."""

from __future__ import annotations

import time
from typing import Callable

import httpx

from app.config import get_settings
from app.services.errors import (
    MISSING_KEY_MESSAGE,
    NETWORK_MESSAGE,
    TIMEOUT_MESSAGE,
    GoogleServiceError,
    classify_google_failure,
)
from app.utils.logger import log_event

PLACES_BASE = "https://places.googleapis.com/v1"
TEXT_SEARCH_URL = f"{PLACES_BASE}/places:searchText"
NEARBY_SEARCH_URL = f"{PLACES_BASE}/places:searchNearby"

# Field masks are the SKU switch. nextPageToken is required on text search or Google omits it.
# regularOpeningHours is included only in detailed mode.
_MINIMAL = [
    "places.id",
    "places.displayName",
    "places.location",
    "places.formattedAddress",
    "places.types",
]
_STANDARD_EXTRA = [
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
    "places.googleMapsUri",
]
_DETAILED_EXTRA = ["places.regularOpeningHours"]

FIELD_MODES = {
    "minimal": list(_MINIMAL),
    "standard": list(_MINIMAL) + list(_STANDARD_EXTRA),
    "detailed": list(_MINIMAL) + list(_STANDARD_EXTRA) + list(_DETAILED_EXTRA),
}

RETRYABLE_STATUS = {429, 500, 503}


def field_mask_for(mode: str, operation: str) -> str:
    selected = FIELD_MODES.get(mode, FIELD_MODES["standard"])
    fields = list(selected)
    if operation == "searchText":
        fields.append("nextPageToken")
    if operation == "placeDetails":
        fields = [item.removeprefix("places.") for item in fields if item != "nextPageToken"]
    return ",".join(fields)


class GooglePlacesClient:
    def __init__(
        self,
        api_key: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = settings.google_maps_api_key if api_key is None else api_key
        self.timeout = settings.google_api_timeout if timeout is None else timeout
        self.max_retries = settings.google_api_max_retries if max_retries is None else max_retries
        self._transport = transport
        self._sleep = sleep or time.sleep
        self._client: httpx.Client | None = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            kwargs: dict = {"timeout": self.timeout}
            if self._transport is not None:
                kwargs["transport"] = self._transport
            self._client = httpx.Client(**kwargs)
        return self._client

    def search_text(self, body: dict, field_mask: str) -> dict:
        return self._request("POST", TEXT_SEARCH_URL, json_body=body, field_mask=field_mask, operation="searchText")

    def search_nearby(self, body: dict, field_mask: str) -> dict:
        return self._request(
            "POST", NEARBY_SEARCH_URL, json_body=body, field_mask=field_mask, operation="searchNearby"
        )

    def place_details(self, place_id: str, field_mask: str) -> dict:
        safe_id = place_id.removeprefix("places/")
        url = f"{PLACES_BASE}/places/{safe_id}"
        return self._request("GET", url, json_body=None, field_mask=field_mask, operation="placeDetails")

    def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict | None,
        field_mask: str,
        operation: str,
    ) -> dict:
        if not (self.api_key or "").strip():
            log_event(
                "error",
                "google_places_failed",
                error_type="invalid_api_key",
                status_code=None,
                operation=operation,
            )
            raise GoogleServiceError("invalid_api_key", MISSING_KEY_MESSAGE, 503, None)

        field_mode = _mode_from_mask(field_mask)
        log_event(
            "info",
            "google_places_request",
            operation=operation,
            field_mode=field_mode,
        )
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": field_mask,
            "Content-Type": "application/json",
        }
        attempt = 0
        while True:
            started = time.perf_counter()
            try:
                response = self._http().request(method, url, headers=headers, json=json_body)
            except httpx.TimeoutException:
                if attempt < self.max_retries:
                    self._backoff(attempt)
                    attempt += 1
                    continue
                log_event(
                    "error",
                    "google_places_failed",
                    error_type="timeout",
                    status_code=None,
                    operation=operation,
                )
                raise GoogleServiceError("timeout", TIMEOUT_MESSAGE, 504, None) from None
            except httpx.TransportError:
                if attempt < self.max_retries:
                    self._backoff(attempt)
                    attempt += 1
                    continue
                log_event(
                    "error",
                    "google_places_failed",
                    error_type="network_error",
                    status_code=None,
                    operation=operation,
                )
                raise GoogleServiceError("network_error", NETWORK_MESSAGE, 502, None) from None

            duration_ms = int((time.perf_counter() - started) * 1000)
            payload = _json_or_empty(response)
            if response.status_code in RETRYABLE_STATUS and attempt < self.max_retries:
                self._backoff(attempt)
                attempt += 1
                continue
            if response.status_code >= 400:
                failure = classify_google_failure(
                    status_code=response.status_code,
                    payload=payload,
                    operation=operation,
                )
                log_event(
                    "error",
                    "google_places_failed",
                    error_type=failure.error_type,
                    status_code=response.status_code,
                    operation=operation,
                    duration_ms=duration_ms,
                )
                failure.duration_ms = duration_ms  # type: ignore[attr-defined]
                raise failure

            count = _result_count(payload)
            log_event(
                "info",
                "google_places_response",
                operation=operation,
                status_code=response.status_code,
                count=count,
                duration_ms=duration_ms,
                field_mode=field_mode,
            )
            payload["_meta"] = {
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "operation": operation,
                "result_count": count,
            }
            return payload

    def _backoff(self, attempt: int) -> None:
        self._sleep(0.4 * (2**attempt))


def _json_or_empty(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _result_count(payload: dict) -> int:
    places = payload.get("places")
    if isinstance(places, list):
        return len(places)
    if payload.get("id"):
        return 1
    return 0


def _mode_from_mask(field_mask: str) -> str:
    if "regularOpeningHours" in field_mask:
        return "detailed"
    if "places.rating" in field_mask or field_mask.startswith("rating") or ",rating," in f",{field_mask},":
        return "standard"
    if "rating" in field_mask:
        return "standard"
    return "minimal"
