from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.utils.validators import (
    clean_business_status,
    clean_category,
    clean_keyword,
    clean_language,
    clean_location,
    clean_radius_km,
    clean_sort,
)


class SearchCreate(BaseModel):
    category: str
    location: str
    radius_km: float | None = 5
    keyword: str | None = None
    max_results: int = Field(default=20, ge=1, le=5000)
    language: str = "en"
    search_mode: Literal["text", "nearby"] = "text"
    min_rating: float | None = Field(default=None, ge=0, le=5)
    min_reviews: int | None = Field(default=None, ge=0)
    business_status: str | None = None
    type_contains: str | None = None
    has_website: bool = False
    has_phone: bool = False
    has_both: bool = False
    max_distance_km: float | None = Field(default=None, ge=0, le=50)
    sort: str = "position_asc"

    @field_validator("category")
    @classmethod
    def _category(cls, value: str) -> str:
        return clean_category(value)

    @field_validator("location")
    @classmethod
    def _location(cls, value: str) -> str:
        return clean_location(value)

    @field_validator("keyword")
    @classmethod
    def _keyword(cls, value: str | None) -> str | None:
        return clean_keyword(value)

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        return clean_language(value)

    @field_validator("radius_km")
    @classmethod
    def _radius(cls, value: float | None) -> float:
        return clean_radius_km(value)

    @field_validator("sort")
    @classmethod
    def _sort(cls, value: str) -> str:
        return clean_sort(value)

    @field_validator("business_status")
    @classmethod
    def _status(cls, value: str | None) -> str | None:
        return clean_business_status(value)

    @field_validator("type_contains")
    @classmethod
    def _type_contains(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = " ".join(value.split())
        return text or None


class BulkRow(BaseModel):
    category: str
    location: str
    radius_km: float | None = None

    @field_validator("category")
    @classmethod
    def _category(cls, value: str) -> str:
        return clean_category(value)

    @field_validator("location")
    @classmethod
    def _location(cls, value: str) -> str:
        return clean_location(value)

    @field_validator("radius_km")
    @classmethod
    def _radius(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return clean_radius_km(value)


class BulkRequest(BaseModel):
    rows: list[BulkRow] | None = None
    csv_text: str | None = None
    confirm: bool = False
    keyword: str | None = None
    max_results: int = Field(default=20, ge=1, le=5000)
    language: str = "en"
    search_mode: Literal["text", "nearby"] = "text"
    min_rating: float | None = Field(default=None, ge=0, le=5)
    min_reviews: int | None = Field(default=None, ge=0)
    business_status: str | None = None
    type_contains: str | None = None
    has_website: bool = False
    has_phone: bool = False
    has_both: bool = False
    max_distance_km: float | None = Field(default=None, ge=0, le=50)
    sort: str = "position_asc"

    @field_validator("keyword")
    @classmethod
    def _keyword(cls, value: str | None) -> str | None:
        return clean_keyword(value)

    @field_validator("language")
    @classmethod
    def _language(cls, value: str) -> str:
        return clean_language(value)

    @field_validator("sort")
    @classmethod
    def _sort(cls, value: str) -> str:
        return clean_sort(value)

    @field_validator("business_status")
    @classmethod
    def _status(cls, value: str | None) -> str | None:
        return clean_business_status(value)


class ViewQuery(BaseModel):
    page: int = 1
    page_size: int = 20
    sort: str = "position_asc"
    min_rating: float | None = None
    min_reviews: int | None = None
    business_status: str | None = None
    type_contains: str | None = None
    q: str | None = None
    has_website: bool = False
    has_phone: bool = False
    has_both: bool = False
    max_distance_km: float | None = None
