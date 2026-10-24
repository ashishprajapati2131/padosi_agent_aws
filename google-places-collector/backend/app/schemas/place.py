from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PlaceOut(BaseModel):
    id: int
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
    types: list[str] = Field(default_factory=list)
    opening_hours: list[str] | None = None
    open_now: bool | None = None
    distance_meters: float | None = None
    position: int | None = None


class SavedPlaceOut(BaseModel):
    id: int
    place_id: int
    created_at: datetime
    place: PlaceOut


class SavePlacesRequest(BaseModel):
    place_id: int | None = None
    place_ids: list[int] | None = None


class ExportCreate(BaseModel):
    search_id: int | None = None
    saved: bool = False
    format: str
    place_ids: list[int] | None = None

    def normalized_format(self) -> str:
        value = (self.format or "").strip().lower()
        if value not in {"csv", "xlsx"}:
            raise ValueError("format")
        return value
