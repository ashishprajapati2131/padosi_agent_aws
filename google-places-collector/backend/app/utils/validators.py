"""Input checks for category and location. Category lists are not hard-coded."""

from __future__ import annotations

import re

from app.services.errors import InputValidationError

_COORD_ONLY = re.compile(r"^\s*-?\d{1,3}(?:\.\d+)?\s*[, ]\s*-?\d{1,3}(?:\.\d+)?\s*$")
_LANGUAGE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")
_SORTS = {
    "position_asc",
    "rating_desc",
    "rating_asc",
    "reviews_desc",
    "name_asc",
    "name_desc",
    "distance_asc",
}
_STATUSES = {"OPERATIONAL", "CLOSED_TEMPORARILY", "CLOSED_PERMANENTLY"}


def clean_category(value: str) -> str:
    text = " ".join((value or "").split())
    if not text:
        raise InputValidationError("Enter a category.")
    if len(text) > 100:
        raise InputValidationError("Category is too long.")
    return text


def clean_location(value: str) -> str:
    text = " ".join((value or "").split())
    if len(text) < 2:
        raise InputValidationError("Enter a location such as a city, area, pincode, or address.")
    if len(text) > 200:
        raise InputValidationError("Location is too long.")
    if _COORD_ONLY.match(text):
        raise InputValidationError("Enter a place name or address. Coordinates are not accepted.")
    return text


def clean_keyword(value: str | None) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    if not text:
        return None
    if len(text) > 100:
        raise InputValidationError("Keyword is too long.")
    return text


def clean_language(value: str | None) -> str:
    text = (value or "en").strip()
    if not _LANGUAGE.match(text):
        raise InputValidationError("Language must look like en or en-IN.")
    return text


def clean_radius_km(value: float | None) -> float:
    radius = 5.0 if value is None else float(value)
    if radius < 0.1 or radius > 50:
        raise InputValidationError("Radius must be between 0.1 and 50 kilometers.")
    return radius


def clean_sort(value: str | None) -> str:
    sort = (value or "position_asc").strip()
    if sort not in _SORTS:
        raise InputValidationError("That sort option is not supported.")
    return sort


def clean_business_status(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    status = str(value).strip().upper()
    if status not in _STATUSES:
        raise InputValidationError("Business status must be operational, closed temporarily, or closed permanently.")
    return status


def category_to_included_type(category: str) -> str:
    """Generic token for Nearby Search. Not a map of business categories."""
    token = re.sub(r"[^a-z0-9]+", "_", category.strip().lower()).strip("_")
    if not token or not re.search(r"[a-z]", token):
        raise InputValidationError(
            "Nearby search needs a category that can be sent as a place type. Use text search for free text."
        )
    return token


def build_text_query(category: str, location: str, keyword: str | None) -> str:
    parts = [category.strip()]
    if keyword and keyword.strip():
        parts.append(keyword.strip())
    parts.append(location.strip())
    return " ".join(parts)
