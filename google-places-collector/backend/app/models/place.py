from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base
from app.models.user import utcnow


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_place_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    # Internal dedup helper (place id, or normalized name + address + rounded coordinates).
    dedupe_key: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    business_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    maps_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    types_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    opening_hours_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_allowed_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
