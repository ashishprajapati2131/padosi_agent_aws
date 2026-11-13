from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.geocoding import GeocodingService
from app.services.providers.factory import get_provider
from app.services.search_service import SearchService


def build_search_service(db: Session) -> SearchService:
    return SearchService(db, get_provider(), GeocodingService())
