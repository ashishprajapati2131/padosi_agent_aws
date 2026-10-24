"""Duplicate removal. Primary key is the Google Place ID; otherwise name + address + rounded coordinates."""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.services.normalized import NormalizedPlace


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return " ".join(cleaned.split())


def fallback_key(
    name: str | None,
    address: str | None,
    latitude: float | None,
    longitude: float | None,
) -> str:
    lat = "" if latitude is None else f"{round(float(latitude), 4):.4f}"
    lng = "" if longitude is None else f"{round(float(longitude), 4):.4f}"
    return f"{normalize_text(name)}|{normalize_text(address)}|{lat}|{lng}"


def place_key(place: NormalizedPlace) -> str:
    if place.google_place_id:
        return f"gid:{place.google_place_id}"
    return "fb:" + fallback_key(place.name, place.address, place.latitude, place.longitude)


def dedupe_places(places: Sequence[NormalizedPlace]) -> tuple[list[NormalizedPlace], int]:
    seen: set[str] = set()
    unique: list[NormalizedPlace] = []
    for place in places:
        key = place_key(place)
        if key in seen:
            continue
        seen.add(key)
        unique.append(place)
    removed = len(places) - len(unique)
    return unique, removed
