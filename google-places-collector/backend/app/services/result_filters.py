"""App-level filters and sorts. None of these orders is Google's ranking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Filterable(Protocol):
    name: str | None
    address: str | None
    rating: float | None
    review_count: int | None
    business_status: str | None
    types: list[str]
    website: str | None
    phone: str | None
    distance_meters: float | None
    position: int


@dataclass
class FilterSpec:
    min_rating: float | None = None
    min_reviews: int | None = None
    business_status: str | None = None
    type_contains: str | None = None
    keyword: str | None = None
    has_website: bool = False
    has_phone: bool = False
    has_both: bool = False
    max_distance_km: float | None = None
    sort: str = "position_asc"


def _present(value: str | None) -> bool:
    return bool(value and value.strip())


def matches(item: Filterable, spec: FilterSpec) -> bool:
    if spec.min_rating is not None:
        if item.rating is None or item.rating < spec.min_rating:
            return False
    if spec.min_reviews is not None:
        if item.review_count is None or item.review_count < spec.min_reviews:
            return False
    if spec.business_status:
        if (item.business_status or "").upper() != spec.business_status.upper():
            return False
    if spec.type_contains:
        needle = spec.type_contains.strip().lower()
        haystack = " ".join(item.types or []).lower()
        if needle not in haystack:
            return False
    if spec.keyword:
        needle = spec.keyword.strip().lower()
        blob = f"{item.name or ''} {item.address or ''}".lower()
        if needle not in blob:
            return False
    if spec.has_website and not _present(item.website):
        return False
    if spec.has_phone and not _present(item.phone):
        return False
    if spec.has_both and not (_present(item.website) and _present(item.phone)):
        return False
    if spec.max_distance_km is not None:
        if item.distance_meters is None or item.distance_meters > spec.max_distance_km * 1000:
            return False
    return True


def apply_filters(items: list, spec: FilterSpec) -> list:
    return [item for item in items if matches(item, spec)]


def _number_key(value: float | int | None, *, descending: bool) -> tuple:
    if value is None:
        return (1, 0, 0)
    ranked = -float(value) if descending else float(value)
    return (0, ranked, 0)


def sort_items(items: list, sort: str) -> list:
    """Sort a copy. Missing values stay at the end. This is not a Google rank."""

    def key(item):
        if sort == "rating_desc":
            return (*_number_key(item.rating, descending=True), item.position)
        if sort == "rating_asc":
            return (*_number_key(item.rating, descending=False), item.position)
        if sort == "reviews_desc":
            return (*_number_key(item.review_count, descending=True), item.position)
        if sort == "name_asc":
            if not item.name:
                return (1, "", item.position)
            return (0, item.name.casefold(), item.position)
        if sort == "name_desc":
            if not item.name:
                return (1, "", item.position)
            # Invert with a prefix so missing names remain last under a normal sort.
            return (0, _invert_text(item.name.casefold()), item.position)
        if sort == "distance_asc":
            return (*_number_key(item.distance_meters, descending=False), item.position)
        return (item.position, (item.name or "").casefold())

    return sorted(items, key=key)


def _invert_text(value: str) -> str:
    return "".join(chr(0x10FFFF - ord(char)) for char in value)
