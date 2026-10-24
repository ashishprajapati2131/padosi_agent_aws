"""Fields this app is willing to persist.

Google Maps Platform terms restrict what you may store and for how long.
Place IDs may be stored and are always kept because they are the dedup key.
Most other content is cacheable only for a limited period — often 30 days.
SEARCH_RETENTION_DAYS is the control. If the current terms are shorter than
the default of 90, lower that setting. Do not add review text, photos, or
other content the terms prohibit storing.

Disable a field without a code change:

    STORAGE_DISABLED_FIELDS=latitude,longitude
"""

from __future__ import annotations

from app.config import get_settings
from app.services.normalized import NormalizedPlace

STORABLE_DEFAULTS = {
    "google_place_id": True,
    "name": True,
    "address": True,
    "latitude": True,
    "longitude": True,
    "rating": True,
    "review_count": True,
    "phone": True,
    "website": True,
    "business_status": True,
    "maps_uri": True,
    "types": True,
    "opening_hours": True,
}

ALWAYS_STORED = frozenset({"google_place_id"})


def storage_enabled(field: str) -> bool:
    if field in ALWAYS_STORED:
        return True
    if not STORABLE_DEFAULTS.get(field, False):
        return False
    return field not in get_settings().storage_disabled()


def stored_value(field: str, value):
    if not storage_enabled(field):
        return None
    return value


def allowed_snapshot(place: NormalizedPlace) -> dict:
    snapshot = {
        "google_place_id": stored_value("google_place_id", place.google_place_id),
        "name": stored_value("name", place.name),
        "address": stored_value("address", place.address),
        "latitude": stored_value("latitude", place.latitude),
        "longitude": stored_value("longitude", place.longitude),
        "rating": stored_value("rating", place.rating),
        "review_count": stored_value("review_count", place.review_count),
        "phone": stored_value("phone", place.phone),
        "website": stored_value("website", place.website),
        "business_status": stored_value("business_status", place.business_status),
        "maps_uri": stored_value("maps_uri", place.maps_uri),
        "types": stored_value("types", list(place.types) if place.types else []),
        "opening_hours": stored_value("opening_hours", place.opening_hours),
    }
    return {key: value for key, value in snapshot.items() if value is not None}
