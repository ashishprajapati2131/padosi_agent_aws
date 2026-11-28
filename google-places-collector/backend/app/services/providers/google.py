"""GooglePlacesProvider — the only PlaceProvider implementation."""

from __future__ import annotations

from app.services.google_places import GooglePlacesClient, field_mask_for
from app.services.normalized import NormalizedPlace, ProviderSearchPage, ProviderSearchRequest


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _clean_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def normalize_place(payload: dict) -> NormalizedPlace:
    """Copy only known fields. Anything Google did not send stays empty."""
    display = payload.get("displayName")
    name = None
    if isinstance(display, dict):
        name = _clean_str(display.get("text"))
    elif isinstance(display, str):
        name = _clean_str(display)

    location = payload.get("location") if isinstance(payload.get("location"), dict) else {}
    types_raw = payload.get("types") if isinstance(payload.get("types"), list) else []
    types = [item for item in types_raw if isinstance(item, str) and item.strip()]

    phone = _clean_str(payload.get("nationalPhoneNumber")) or _clean_str(payload.get("internationalPhoneNumber"))
    website = _clean_str(payload.get("websiteUri"))
    maps_uri = _clean_str(payload.get("googleMapsUri"))
    if maps_uri and not maps_uri.startswith(("http://", "https://")):
        maps_uri = None
    if website and not website.startswith(("http://", "https://")):
        website = None

    opening = None
    hours = payload.get("regularOpeningHours")
    if isinstance(hours, dict):
        descriptions = hours.get("weekdayDescriptions")
        lines = [item.strip() for item in descriptions if isinstance(item, str) and item.strip()] if isinstance(descriptions, list) else []
        open_now = hours.get("openNow") if isinstance(hours.get("openNow"), bool) else None
        if lines or open_now is not None:
            opening = {"weekday_descriptions": lines, "open_now": open_now}

    place_id = _clean_str(payload.get("id"))
    return NormalizedPlace(
        google_place_id=place_id,
        name=name,
        address=_clean_str(payload.get("formattedAddress")),
        latitude=_as_float(location.get("latitude")),
        longitude=_as_float(location.get("longitude")),
        rating=_as_float(payload.get("rating")),
        review_count=_as_int(payload.get("userRatingCount")),
        phone=phone,
        website=website,
        business_status=_clean_str(payload.get("businessStatus")),
        maps_uri=maps_uri,
        types=types,
        opening_hours=opening,
    )


class GooglePlacesProvider:
    def __init__(self, client: GooglePlacesClient | None = None) -> None:
        self.client = client or GooglePlacesClient()

    def search(self, request: ProviderSearchRequest) -> ProviderSearchPage:
        if request.mode == "nearby":
            operation = "searchNearby"
            mask = field_mask_for(request.field_mode, operation)
            body: dict = {
                "includedTypes": request.included_types or [],
                "maxResultCount": max(1, min(request.page_size, 20)),
                "languageCode": request.language,
                "locationRestriction": {
                    "circle": {
                        "center": {"latitude": request.latitude, "longitude": request.longitude},
                        "radius": float(request.radius_meters),
                    }
                },
            }
            payload = self.client.search_nearby(body, mask)
        else:
            operation = "searchText"
            mask = field_mask_for(request.field_mode, operation)
            body = {
                "textQuery": request.text_query or "",
                "pageSize": max(1, min(request.page_size, 20)),
                "languageCode": request.language,
                "locationBias": {
                    "circle": {
                        "center": {"latitude": request.latitude, "longitude": request.longitude},
                        "radius": float(request.radius_meters),
                    }
                },
            }
            if request.page_token:
                body["pageToken"] = request.page_token
            payload = self.client.search_text(body, mask)

        raw_places = payload.get("places") if isinstance(payload.get("places"), list) else []
        places = [normalize_place(item) for item in raw_places if isinstance(item, dict)]
        token = payload.get("nextPageToken")
        meta = payload.get("_meta") if isinstance(payload.get("_meta"), dict) else {}
        return ProviderSearchPage(
            places=places,
            next_page_token=token if isinstance(token, str) and token else None,
            status_code=int(meta.get("status_code") or 200),
            duration_ms=int(meta.get("duration_ms") or 0),
            operation=operation,
            result_count=len(places),
        )

    def get_details(self, place_id: str, field_mode: str) -> NormalizedPlace:
        # Place details always uses the detailed mask when the caller asks for a place.
        mode = field_mode if field_mode in {"minimal", "standard", "detailed"} else "detailed"
        mask = field_mask_for(mode, "placeDetails")
        payload = self.client.place_details(place_id, mask)
        return normalize_place(payload)
