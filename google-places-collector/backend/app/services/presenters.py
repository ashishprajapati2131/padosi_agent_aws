"""Turn stored rows into API objects. Missing values stay null for the UI to label."""

from __future__ import annotations

from app.models import Place, Search, SearchResult
from app.services.result_filters import FilterSpec, apply_filters, sort_items
from app.services.storage_policy import storage_enabled
from app.utils.pagination import slice_page

_MODE_FIELDS = {
    "minimal": ["name", "address", "latitude", "longitude", "types", "place_id"],
    "standard": [
        "name",
        "address",
        "latitude",
        "longitude",
        "types",
        "place_id",
        "phone",
        "website",
        "rating",
        "review_count",
        "business_status",
        "maps_uri",
    ],
    "detailed": [
        "name",
        "address",
        "latitude",
        "longitude",
        "types",
        "place_id",
        "phone",
        "website",
        "rating",
        "review_count",
        "business_status",
        "maps_uri",
        "opening_hours",
    ],
}

_STORAGE_NAME = {
    "place_id": "google_place_id",
    "types": "types",
    "opening_hours": "opening_hours",
}


def available_fields(field_mode: str) -> list[str]:
    fields = list(_MODE_FIELDS.get(field_mode, _MODE_FIELDS["standard"]))
    visible = []
    for field in fields:
        storage_name = _STORAGE_NAME.get(field, field)
        if storage_enabled(storage_name):
            visible.append(field)
    if "latitude" in visible and "longitude" in visible:
        visible.append("distance")
    return visible


class StoredItem:
    def __init__(self, place: Place, result: SearchResult) -> None:
        self.place = place
        self.result = result
        self.name = place.name
        self.address = place.address
        self.rating = place.rating
        self.review_count = place.review_count
        self.business_status = place.business_status
        self.types = list(place.types_json or [])
        self.website = place.website
        self.phone = place.phone
        self.distance_meters = result.distance_meters
        self.position = result.position
        self.latitude = place.latitude
        self.longitude = place.longitude


def place_dict(place: Place, result: SearchResult | None = None) -> dict:
    hours = place.opening_hours_json if isinstance(place.opening_hours_json, dict) else None
    descriptions = None
    open_now = None
    if hours:
        raw = hours.get("weekday_descriptions")
        if isinstance(raw, list) and raw:
            descriptions = [str(item) for item in raw]
        if isinstance(hours.get("open_now"), bool):
            open_now = hours["open_now"]
    return {
        "id": place.id,
        "google_place_id": place.google_place_id,
        "name": place.name,
        "address": place.address,
        "latitude": place.latitude,
        "longitude": place.longitude,
        "rating": place.rating,
        "review_count": place.review_count,
        "phone": place.phone,
        "website": place.website,
        "business_status": place.business_status,
        "maps_uri": place.maps_uri,
        "types": list(place.types_json or []),
        "opening_hours": descriptions,
        "open_now": open_now,
        "distance_meters": None if result is None else result.distance_meters,
        "position": None if result is None else result.position,
    }


def search_dict(search: Search) -> dict:
    return {
        "id": search.id,
        "query": search.query,
        "category": search.category,
        "location_text": search.location_text,
        "formatted_address": search.formatted_address,
        "latitude": search.latitude,
        "longitude": search.longitude,
        "radius_meters": search.radius_meters,
        "keyword": search.keyword,
        "language": search.language,
        "search_mode": search.search_mode,
        "field_mode": search.field_mode,
        "result_count": search.result_count,
        "status": search.status,
        "error_message": search.error_message,
        "created_at": search.created_at,
        "available_fields": available_fields(search.field_mode),
    }


def view_spec_from_query(
    *,
    sort: str = "position_asc",
    min_rating: float | None = None,
    min_reviews: int | None = None,
    business_status: str | None = None,
    type_contains: str | None = None,
    q: str | None = None,
    has_website: bool = False,
    has_phone: bool = False,
    has_both: bool = False,
    max_distance_km: float | None = None,
) -> FilterSpec:
    return FilterSpec(
        min_rating=min_rating,
        min_reviews=min_reviews,
        business_status=business_status,
        type_contains=type_contains,
        keyword=(q or "").strip() or None,
        has_website=has_website,
        has_phone=has_phone,
        has_both=has_both,
        max_distance_km=max_distance_km,
        sort=sort or "position_asc",
    )


def project_results(rows: list[tuple[SearchResult, Place]], spec: FilterSpec, page: int, page_size: int) -> dict:
    items = [StoredItem(place, result) for result, place in rows]
    filtered = apply_filters(items, spec)
    ordered = sort_items(filtered, spec.sort)
    chunk, total = slice_page(ordered, page, page_size)
    return {
        "results": [place_dict(item.place, item.result) for item in chunk],
        "page": page if page >= 1 else 1,
        "page_size": page_size,
        "total": total,
    }
