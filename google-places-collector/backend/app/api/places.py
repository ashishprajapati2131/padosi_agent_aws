from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.connection import get_db
from app.models import Place, SavedPlace, Search, SearchResult, User
from app.schemas.place import SavePlacesRequest
from app.services.errors import GoogleServiceError
from app.services.presenters import place_dict
from app.services.rate_limit import limiter
from app.services.usage import record_usage
from app.utils.logger import log_event

router = APIRouter(tags=["places"])


def _can_view(db: Session, user: User, place_id: int) -> bool:
    if user.role == "admin":
        return True
    saved = db.query(SavedPlace.id).filter(SavedPlace.user_id == user.id, SavedPlace.place_id == place_id).first()
    if saved:
        return True
    linked = (
        db.query(SearchResult.id)
        .join(Search, Search.id == SearchResult.search_id)
        .filter(SearchResult.place_id == place_id, Search.user_id == user.id)
        .first()
    )
    return linked is not None


@router.get("/places/{place_id}")
def place_details(
    place_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    place = db.get(Place, place_id)
    if place is None or not _can_view(db, user, place.id):
        raise HTTPException(status_code=404, detail="Place not found.")
    warning = None
    source = "stored"
    if place.google_place_id:
        limiter.reserve_details(user.id)
        started = time.perf_counter()
        try:
            from app.services import container
            from app.services.providers import factory as provider_factory

            provider = provider_factory.get_provider()
            fresh = provider.get_details(place.google_place_id, "detailed")
            service = container.build_search_service(db)
            service._copy_fields(place, fresh, place.dedupe_key or "")
            if fresh.google_place_id:
                from app.services.deduplication import place_key

                place.dedupe_key = place_key(fresh)
            db.commit()
            db.refresh(place)
            record_usage(
                db,
                user_id=user.id,
                endpoint="places",
                search_type="details",
                google_operation="placeDetails",
                success=True,
                status_code=200,
                duration_ms=int((time.perf_counter() - started) * 1000),
                result_count=1,
            )
            db.commit()
            source = "google"
        except GoogleServiceError as exc:
            record_usage(
                db,
                user_id=user.id,
                endpoint="places",
                search_type="details",
                google_operation="placeDetails",
                success=False,
                status_code=exc.google_status,
                duration_ms=int((time.perf_counter() - started) * 1000),
                result_count=0,
                error_type=exc.error_type,
            )
            db.commit()
            warning = exc.message
            log_event("error", "place_details_failed", error_type=exc.error_type, status_code=exc.google_status)
    body = place_dict(place)
    body["detail_source"] = source
    body["detail_warning"] = warning
    return body


@router.get("/saved-places")
def list_saved(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = 1,
    page_size: int = 20,
) -> dict:
    query = db.query(SavedPlace).filter(SavedPlace.user_id == user.id).order_by(SavedPlace.created_at.desc())
    total = query.count()
    size = min(max(page_size, 1), 100)
    current = max(page, 1)
    rows = query.offset((current - 1) * size).limit(size).all()
    items = []
    for saved in rows:
        place = db.get(Place, saved.place_id)
        if place is None:
            continue
        items.append(
            {
                "id": saved.id,
                "place_id": saved.place_id,
                "created_at": saved.created_at,
                "place": place_dict(place),
            }
        )
    return {"results": items, "page": current, "page_size": size, "total": total}


@router.post("/saved-places")
def save_places(
    body: SavePlacesRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ids = list(body.place_ids or [])
    if body.place_id is not None:
        ids.append(body.place_id)
    if not ids:
        raise HTTPException(status_code=422, detail="Choose at least one place to save.")
    saved_ids = []
    for place_id in dict.fromkeys(ids):
        if not _can_view(db, user, place_id):
            continue
        existing = (
            db.query(SavedPlace).filter(SavedPlace.user_id == user.id, SavedPlace.place_id == place_id).one_or_none()
        )
        if existing is None:
            existing = SavedPlace(user_id=user.id, place_id=place_id)
            db.add(existing)
            db.flush()
        saved_ids.append(existing.id)
    if not saved_ids:
        raise HTTPException(status_code=404, detail="Place not found.")
    db.commit()
    return {"saved_ids": saved_ids}


@router.delete("/saved-places/{saved_id}", status_code=204)
def delete_saved(
    saved_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    saved = db.get(SavedPlace, saved_id)
    if saved is None or saved.user_id != user.id:
        raise HTTPException(status_code=404, detail="Saved place not found.")
    db.delete(saved)
    db.commit()
