"""Search flow. Calls the provider and geocoder — never raw HTTP."""

from __future__ import annotations

import time

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Place, Search, SearchResult, User
from app.schemas.search import SearchCreate
from app.services.deduplication import dedupe_places, place_key
from app.services.distance import haversine_meters
from app.services.errors import (
    ZERO_RESULTS_MESSAGE,
    AppError,
    GoogleServiceError,
    LocationNotFoundError,
)
from app.services.normalized import NormalizedPlace
from app.services.presenters import project_results, search_dict, view_spec_from_query
from app.services.providers.base import PlaceProvider
from app.services.rate_limit import limiter
from app.services.result_filters import FilterSpec, apply_filters, sort_items
from app.services.storage_policy import allowed_snapshot, storage_enabled
from app.services.usage import record_usage
from app.utils.logger import log_event
from app.utils.validators import build_text_query, category_to_included_type


class SearchService:
    def __init__(self, db: Session, provider: PlaceProvider, geocoder) -> None:
        self.db = db
        self.provider = provider
        self.geocoder = geocoder

    def execute(self, user: User, payload: SearchCreate, client_ip: str, *, charge_rate_limit: bool = True) -> dict:
        if charge_rate_limit:
            limiter.reserve_search(user.id, client_ip, cost=1)
        settings = get_settings()
        applied_cap = min(payload.max_results, settings.max_results_per_search)
        radius_meters = int(round(payload.radius_km * 1000))
        field_mode = settings.google_places_field_mode
        if payload.search_mode == "text":
            query = build_text_query(payload.category, payload.location, payload.keyword)
        else:
            query = f"{payload.category} near {payload.location}"
            if payload.keyword:
                query = f"{payload.category} {payload.keyword} near {payload.location}"

        search = Search(
            user_id=user.id,
            query=query[:400],
            category=payload.category,
            location_text=payload.location,
            radius_meters=radius_meters,
            keyword=payload.keyword,
            language=payload.language,
            search_mode=payload.search_mode,
            filters_json=_stored_filters(payload),
            field_mode=field_mode,
            result_count=0,
            status="running",
        )
        self.db.add(search)
        self.db.flush()
        log_event(
            "info",
            "search_started",
            search_id=search.id,
            user_id=user.id,
            category=payload.category,
            location=payload.location,
            search_mode=payload.search_mode,
            field_mode=field_mode,
        )
        try:
            if payload.search_mode == "nearby":
                category_to_included_type(payload.category)
            geo = self._geocode(user, payload.location)
            search.latitude = geo.latitude
            search.longitude = geo.longitude
            search.formatted_address = geo.formatted_address[:400]
            log_event(
                "info",
                "location_resolved",
                search_id=search.id,
                formatted_address=search.formatted_address,
                latitude=geo.latitude,
                longitude=geo.longitude,
            )
            collected = self._collect(
                user,
                payload,
                latitude=geo.latitude,
                longitude=geo.longitude,
                radius_meters=radius_meters,
                field_mode=field_mode,
                query=query,
                limit=applied_cap,
            )
            log_event("info", "results_normalized", search_id=search.id, count=len(collected))
            unique, removed = dedupe_places(collected)
            log_event("info", "duplicates_removed", search_id=search.id, removed=removed, remaining=len(unique))
            for item in unique:
                if item.latitude is not None and item.longitude is not None:
                    item.distance_meters = haversine_meters(
                        geo.latitude, geo.longitude, item.latitude, item.longitude
                    )
            for index, item in enumerate(unique, start=1):
                item.position = index
            spec = _filter_spec(payload)
            kept = apply_filters(unique, spec)
            ranked = sort_items(kept, payload.sort)
            for index, item in enumerate(ranked, start=1):
                item.position = index
            self._persist_results(search, ranked)
            search.status = "completed"
            search.result_count = len(ranked)
            search.error_message = None
            self.db.commit()
            self.db.refresh(search)
        except AppError as exc:
            search.status = "failed"
            search.error_message = exc.message
            search.result_count = 0
            self.db.commit()
            exc.search_id = search.id
            raise
        body = self._response(search, page=1, page_size=20)
        if payload.max_results > applied_cap:
            body["cap_note"] = f"Results are limited to {applied_cap} places per search."
        if search.result_count == 0:
            body["message"] = ZERO_RESULTS_MESSAGE
        else:
            body["message"] = None
        body["max_results_applied"] = applied_cap
        return body

    def rerun(self, user: User, search: Search, client_ip: str) -> dict:
        stored = search.filters_json or {}
        payload = SearchCreate(
            category=search.category,
            location=search.location_text,
            radius_km=(search.radius_meters or 5000) / 1000,
            keyword=search.keyword,
            max_results=int(stored.get("max_results") or 20),
            language=search.language or "en",
            search_mode=search.search_mode if search.search_mode in {"text", "nearby"} else "text",
            min_rating=stored.get("min_rating"),
            min_reviews=stored.get("min_reviews"),
            business_status=stored.get("business_status"),
            type_contains=stored.get("type_contains"),
            has_website=bool(stored.get("has_website")),
            has_phone=bool(stored.get("has_phone")),
            has_both=bool(stored.get("has_both")),
            max_distance_km=stored.get("max_distance_km"),
            sort=stored.get("sort") or "position_asc",
        )
        return self.execute(user, payload, client_ip)

    def _geocode(self, user: User, location: str):
        started = time.perf_counter()
        try:
            result = self.geocoder.geocode(location)
        except LocationNotFoundError:
            record_usage(
                self.db,
                user_id=user.id,
                endpoint="geocode",
                search_type="geocode",
                google_operation="geocode",
                success=True,
                status_code=200,
                duration_ms=int((time.perf_counter() - started) * 1000),
                result_count=0,
                error_type="location_not_found",
            )
            raise
        except GoogleServiceError as exc:
            record_usage(
                self.db,
                user_id=user.id,
                endpoint="geocode",
                search_type="geocode",
                google_operation="geocode",
                success=False,
                status_code=exc.google_status,
                duration_ms=int((time.perf_counter() - started) * 1000),
                result_count=0,
                error_type=exc.error_type,
            )
            raise
        record_usage(
            self.db,
            user_id=user.id,
            endpoint="geocode",
            search_type="geocode",
            google_operation="geocode",
            success=True,
            status_code=result.status_code,
            duration_ms=result.duration_ms,
            result_count=1,
        )
        return result

    def _collect(
        self,
        user: User,
        payload: SearchCreate,
        *,
        latitude: float,
        longitude: float,
        radius_meters: int,
        field_mode: str,
        query: str,
        limit: int,
    ) -> list[NormalizedPlace]:
        from app.services.normalized import ProviderSearchRequest

        included = None
        if payload.search_mode == "nearby":
            included = [category_to_included_type(payload.category)]
        collected: list[NormalizedPlace] = []
        token: str | None = None
        seen_tokens: set[str] = set()
        while len(collected) < limit:
            page_size = min(20, limit - len(collected))
            if token:
                if token in seen_tokens:
                    break
                seen_tokens.add(token)
            request = ProviderSearchRequest(
                mode=payload.search_mode,
                text_query=query if payload.search_mode == "text" else None,
                included_types=included,
                latitude=latitude,
                longitude=longitude,
                radius_meters=float(radius_meters),
                language=payload.language,
                page_token=token,
                page_size=page_size,
                field_mode=field_mode,
            )
            started = time.perf_counter()
            try:
                page = self.provider.search(request)
            except GoogleServiceError as exc:
                record_usage(
                    self.db,
                    user_id=user.id,
                    endpoint="places",
                    search_type=payload.search_mode,
                    google_operation="searchNearby" if payload.search_mode == "nearby" else "searchText",
                    success=False,
                    status_code=exc.google_status,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    result_count=0,
                    error_type=exc.error_type,
                )
                raise
            record_usage(
                self.db,
                user_id=user.id,
                endpoint="places",
                search_type=payload.search_mode,
                google_operation=page.operation,
                success=True,
                status_code=page.status_code,
                duration_ms=page.duration_ms,
                result_count=page.result_count,
            )
            if not page.places:
                break
            room = limit - len(collected)
            collected.extend(page.places[:room])
            token = page.next_page_token
            if not token:
                break
            if payload.search_mode == "nearby" and token is None:
                break
        return collected[:limit]

    def _persist_results(self, search: Search, ranked: list[NormalizedPlace]) -> None:
        for item in ranked:
            row = self._upsert_place(item)
            self.db.add(
                SearchResult(
                    search_id=search.id,
                    place_id=row.id,
                    distance_meters=item.distance_meters,
                    position=item.position,
                )
            )

    def _upsert_place(self, item: NormalizedPlace) -> Place:
        key = place_key(item)
        existing = None
        if item.google_place_id:
            existing = self.db.query(Place).filter(Place.google_place_id == item.google_place_id).one_or_none()
        if existing is None:
            existing = self.db.query(Place).filter(Place.dedupe_key == key).one_or_none()
        if existing is None:
            existing = Place(dedupe_key=key)
            self._copy_fields(existing, item, key)
            nested = self.db.begin_nested()
            try:
                self.db.add(existing)
                self.db.flush()
                nested.commit()
            except IntegrityError:
                nested.rollback()
                if item.google_place_id:
                    existing = self.db.query(Place).filter(Place.google_place_id == item.google_place_id).one()
                else:
                    existing = self.db.query(Place).filter(Place.dedupe_key == key).one()
                self._copy_fields(existing, item, key)
            return existing
        self._copy_fields(existing, item, key)
        self.db.flush()
        return existing

    def _copy_fields(self, row: Place, item: NormalizedPlace, key: str) -> None:
        row.dedupe_key = key
        if item.google_place_id and storage_enabled("google_place_id"):
            row.google_place_id = item.google_place_id
        if storage_enabled("name") and item.name:
            row.name = item.name
        if storage_enabled("address") and item.address:
            row.address = item.address
        if storage_enabled("latitude") and item.latitude is not None:
            row.latitude = item.latitude
        if storage_enabled("longitude") and item.longitude is not None:
            row.longitude = item.longitude
        if storage_enabled("rating") and item.rating is not None:
            row.rating = item.rating
        if storage_enabled("review_count") and item.review_count is not None:
            row.review_count = item.review_count
        if storage_enabled("phone") and item.phone:
            row.phone = item.phone
        if storage_enabled("website") and item.website:
            row.website = item.website
        if storage_enabled("business_status") and item.business_status:
            row.business_status = item.business_status
        if storage_enabled("maps_uri") and item.maps_uri:
            row.maps_uri = item.maps_uri
        if storage_enabled("types") and item.types:
            row.types_json = list(item.types)
        if storage_enabled("opening_hours") and item.opening_hours:
            row.opening_hours_json = item.opening_hours
        row.raw_allowed_json = allowed_snapshot(item)

    def load_pairs(self, search: Search) -> list[tuple[SearchResult, Place]]:
        rows = (
            self.db.query(SearchResult, Place)
            .join(Place, Place.id == SearchResult.place_id)
            .filter(SearchResult.search_id == search.id)
            .all()
        )
        return list(rows)

    def _response(self, search: Search, *, page: int, page_size: int, spec: FilterSpec | None = None) -> dict:
        active = spec or FilterSpec(sort="position_asc")
        projected = project_results(self.load_pairs(search), active, page, page_size)
        body = {
            "search": search_dict(search),
            **projected,
            "message": ZERO_RESULTS_MESSAGE if search.status == "completed" and search.result_count == 0 else None,
        }
        return body

    def read(self, search: Search, *, page: int, page_size: int, spec: FilterSpec) -> dict:
        return self._response(search, page=page, page_size=page_size, spec=spec)


def _stored_filters(payload: SearchCreate) -> dict:
    return {
        "min_rating": payload.min_rating,
        "min_reviews": payload.min_reviews,
        "business_status": payload.business_status,
        "type_contains": payload.type_contains,
        "has_website": payload.has_website,
        "has_phone": payload.has_phone,
        "has_both": payload.has_both,
        "max_distance_km": payload.max_distance_km,
        "max_results": payload.max_results,
        "sort": payload.sort,
    }


def _filter_spec(payload: SearchCreate) -> FilterSpec:
    return view_spec_from_query(
        sort=payload.sort,
        min_rating=payload.min_rating,
        min_reviews=payload.min_reviews,
        business_status=payload.business_status,
        type_contains=payload.type_contains,
        q=None,
        has_website=payload.has_website,
        has_phone=payload.has_phone,
        has_both=payload.has_both,
        max_distance_km=payload.max_distance_km,
    )
