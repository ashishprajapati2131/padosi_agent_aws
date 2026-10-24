"""Export columns. Only these keys can appear in CSV or XLSX files.

Each field is flagged so an operator can turn it off without editing code:

    EXPORT_DISABLED_FIELDS=latitude,longitude
    EXPORT_FIELD_FLAGS={"phone": false}

The default list is the product allowlist. It is policy, not a dump of the
Google payload. Review it when Maps Platform terms change. Fields disabled
in the storage policy are also omitted, because they were not persisted.

Headers are the field keys so a disabled column is unambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings

# key, enabled by default
EXPORT_FIELD_DEFAULTS: list[tuple[str, bool]] = [
    ("name", True),
    ("address", True),
    ("phone", True),
    ("website", True),
    ("rating", True),
    ("review_count", True),
    ("place_id", True),
    ("latitude", True),
    ("longitude", True),
    ("business_status", True),
    ("maps_uri", True),
]

# Storage keys that gate an export key. place_id maps to google_place_id.
_STORAGE_GATE = {
    "name": "name",
    "address": "address",
    "phone": "phone",
    "website": "website",
    "rating": "rating",
    "review_count": "review_count",
    "place_id": "google_place_id",
    "latitude": "latitude",
    "longitude": "longitude",
    "business_status": "business_status",
    "maps_uri": "maps_uri",
}


@dataclass(frozen=True)
class ExportField:
    key: str
    enabled: bool


def enabled_export_fields() -> list[ExportField]:
    from app.services.storage_policy import storage_enabled

    disabled = get_settings().export_disabled()
    fields: list[ExportField] = []
    for key, default_on in EXPORT_FIELD_DEFAULTS:
        allowed = default_on and key not in disabled and storage_enabled(_STORAGE_GATE[key])
        if allowed:
            fields.append(ExportField(key=key, enabled=True))
    return fields
