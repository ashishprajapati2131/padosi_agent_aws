"""The only module that calls the Geocoding API over HTTP."""

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
    LocationNotFoundError,
    classify_google_failure,
)
from app.services.normalized import GeocodeResult
from app.utils.logger import log_event

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


class GeocodingService:
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

    def geocode(self, location: str) -> GeocodeResult:
        if not (self.api_key or "").strip():
            log_event("error", "google_places_failed", error_type="invalid_api_key", status_code=None, operation="geocode")
            raise GoogleServiceError("invalid_api_key", MISSING_KEY_MESSAGE, 503, None)

        log_event("info", "google_places_request", operation="geocode", field_mode="geocode")
        params = {"address": location, "key": self.api_key}
        attempt = 0
        while True:
            started = time.perf_counter()
            try:
                response = self._http().get(GEOCODE_URL, params=params)
            except httpx.TimeoutException:
                if attempt < self.max_retries:
                    self._sleep(0.4 * (2**attempt))
                    attempt += 1
                    continue
                log_event("error", "google_places_failed", error_type="timeout", status_code=None, operation="geocode")
                raise GoogleServiceError("timeout", TIMEOUT_MESSAGE, 504, None) from None
            except httpx.TransportError:
                if attempt < self.max_retries:
                    self._sleep(0.4 * (2**attempt))
                    attempt += 1
                    continue
                log_event(
                    "error", "google_places_failed", error_type="network_error", status_code=None, operation="geocode"
                )
                raise GoogleServiceError("network_error", NETWORK_MESSAGE, 502, None) from None

            duration_ms = int((time.perf_counter() - started) * 1000)
            if response.status_code in {429, 500, 503} and attempt < self.max_retries:
                self._sleep(0.4 * (2**attempt))
                attempt += 1
                continue
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}

            if response.status_code >= 400:
                failure = classify_google_failure(status_code=response.status_code, payload=payload, operation="geocode")
                log_event(
                    "error",
                    "google_places_failed",
                    error_type=failure.error_type,
                    status_code=response.status_code,
                    operation="geocode",
                    duration_ms=duration_ms,
                )
                raise failure

            status = str(payload.get("status") or "")
            if status == "OK":
                results = payload.get("results") or []
                if not results:
                    raise LocationNotFoundError()
                first = results[0]
                geometry = (first.get("geometry") or {}).get("location") or {}
                lat = geometry.get("lat")
                lng = geometry.get("lng")
                formatted = first.get("formatted_address")
                if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)) or not formatted:
                    raise LocationNotFoundError()
                log_event(
                    "info",
                    "google_places_response",
                    operation="geocode",
                    status_code=response.status_code,
                    count=1,
                    duration_ms=duration_ms,
                )
                return GeocodeResult(
                    latitude=float(lat),
                    longitude=float(lng),
                    formatted_address=str(formatted),
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
            if status == "ZERO_RESULTS":
                log_event(
                    "info",
                    "google_places_response",
                    operation="geocode",
                    status_code=response.status_code,
                    count=0,
                    duration_ms=duration_ms,
                )
                raise LocationNotFoundError()
            if status == "UNKNOWN_ERROR" and attempt < self.max_retries:
                self._sleep(0.4 * (2**attempt))
                attempt += 1
                continue
            failure = classify_google_failure(
                status_code=response.status_code,
                payload={"status": status, "error_message": payload.get("error_message")},
                operation="geocode",
            )
            log_event(
                "error",
                "google_places_failed",
                error_type=failure.error_type,
                status_code=response.status_code,
                operation="geocode",
                duration_ms=duration_ms,
            )
            raise failure
