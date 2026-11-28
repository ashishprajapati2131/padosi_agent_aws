"""Client-safe errors. Messages never include keys, paths, or upstream bodies."""

from __future__ import annotations


class AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_type: str,
        status_code: int,
        search_id: int | None = None,
        google_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.status_code = status_code
        self.search_id = search_id
        self.google_status = google_status


class InputValidationError(ValueError, AppError):
    def __init__(self, message: str) -> None:
        AppError.__init__(self, message, error_type="invalid_request", status_code=422)


class LocationNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "We could not resolve that location. Try a city, area, pincode, or a fuller address.",
            error_type="location_not_found",
            status_code=422,
        )


class RateLimitError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_type="rate_limit", status_code=429)


class GoogleServiceError(AppError):
    def __init__(
        self,
        error_type: str,
        message: str,
        status_code: int = 502,
        google_status: int | None = None,
    ) -> None:
        super().__init__(
            message,
            error_type=error_type,
            status_code=status_code,
            google_status=google_status,
        )


QUOTA_MESSAGE = "Google Places API quota has been exceeded. Please try again later."
INVALID_KEY_MESSAGE = "The Google API key is invalid. Check the server configuration."
MISSING_KEY_MESSAGE = "Google Maps API key is not configured on the server."
BILLING_MESSAGE = "Google Maps Platform billing is not enabled for this project."
PERMISSION_MESSAGE = "The Google API is not enabled for this key, or the key does not have permission."
INVALID_REQUEST_MESSAGE = "The search request was rejected. Check the category, location, and filters."
NEARBY_TYPE_MESSAGE = (
    "Nearby search did not accept that category as a place type. "
    "Switch to text search for a free-text category."
)
TIMEOUT_MESSAGE = "The request to Google timed out. Please try again."
NETWORK_MESSAGE = "Could not reach Google. Check the network and try again."
GENERIC_GOOGLE_MESSAGE = "Google Places could not complete this search. Please try again later."
ZERO_RESULTS_MESSAGE = "No places found for this search."

FATAL_GOOGLE_TYPES = frozenset(
    {"quota_exceeded", "invalid_api_key", "billing_disabled", "permission_denied"}
)


def classify_google_failure(
    *,
    status_code: int | None,
    payload: dict | None,
    operation: str,
) -> GoogleServiceError:
    """Map a Google HTTP payload to a fixed client message. Ignores raw text."""
    body = payload or {}
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    google_status = str(error.get("status") or body.get("status") or "")
    message = str(error.get("message") or body.get("error_message") or "")
    blob = f"{google_status} {message}".lower()

    if "api key" in blob or status_code == 401:
        return GoogleServiceError("invalid_api_key", INVALID_KEY_MESSAGE, 502, status_code)
    if "billing" in blob:
        return GoogleServiceError("billing_disabled", BILLING_MESSAGE, 502, status_code)
    if (
        status_code == 429
        or "resource_exhausted" in blob
        or "over_query_limit" in blob
        or "over_daily_limit" in blob
        or "quota" in blob
    ):
        return GoogleServiceError("quota_exceeded", QUOTA_MESSAGE, 429, status_code)
    if (
        status_code == 403
        or "permission_denied" in blob
        or "not authorized" in blob
        or "has not been used" in blob
        or "api is not activated" in blob
    ):
        return GoogleServiceError("permission_denied", PERMISSION_MESSAGE, 502, status_code)
    if status_code == 400 or google_status in {"INVALID_ARGUMENT", "INVALID_REQUEST"}:
        if operation == "searchNearby" and ("included" in blob or "type" in blob):
            return GoogleServiceError("invalid_request", NEARBY_TYPE_MESSAGE, 422, status_code)
        return GoogleServiceError("invalid_request", INVALID_REQUEST_MESSAGE, 422, status_code)
    if google_status == "REQUEST_DENIED":
        return GoogleServiceError("permission_denied", PERMISSION_MESSAGE, 502, status_code)
    return GoogleServiceError("google_error", GENERIC_GOOGLE_MESSAGE, 502, status_code)
