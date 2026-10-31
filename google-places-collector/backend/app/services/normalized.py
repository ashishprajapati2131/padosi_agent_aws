from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NormalizedPlace:
    google_place_id: str | None = None
    name: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    rating: float | None = None
    review_count: int | None = None
    phone: str | None = None
    website: str | None = None
    business_status: str | None = None
    maps_uri: str | None = None
    types: list[str] = field(default_factory=list)
    opening_hours: dict | None = None
    distance_meters: float | None = None
    position: int = 0


@dataclass
class GeocodeResult:
    latitude: float
    longitude: float
    formatted_address: str
    status_code: int
    duration_ms: int


@dataclass
class ProviderSearchRequest:
    mode: str
    text_query: str | None
    included_types: list[str] | None
    latitude: float
    longitude: float
    radius_meters: float
    language: str
    page_token: str | None
    page_size: int
    field_mode: str


@dataclass
class ProviderSearchPage:
    places: list[NormalizedPlace]
    next_page_token: str | None
    status_code: int
    duration_ms: int
    operation: str
    result_count: int
