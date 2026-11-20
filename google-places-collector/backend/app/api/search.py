from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user, owned_search
from app.database.connection import get_db
from app.models import User
from app.schemas.search import BulkRequest, SearchCreate
from app.services.bulk_service import run_bulk
from app.services.presenters import view_spec_from_query
from app.utils.pagination import window
from app.utils.validators import clean_sort

router = APIRouter(tags=["search"])


def _service(db: Session):
    from app.services import container

    return container.build_search_service(db)


def _run(db: Session, user: User, payload: SearchCreate, ip: str) -> dict:
    return _service(db).execute(user, payload, ip)


@router.post("/search")
def create_search(
    body: SearchCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return _run(db, user, body, client_ip(request))


@router.get("/search/{search_id}")
def get_search(
    search_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort: str = Query("position_asc"),
    min_rating: float | None = Query(None, ge=0, le=5),
    min_reviews: int | None = Query(None, ge=0),
    business_status: str | None = None,
    type_contains: str | None = None,
    q: str | None = None,
    has_website: bool = False,
    has_phone: bool = False,
    has_both: bool = False,
    max_distance_km: float | None = Query(None, ge=0, le=50),
) -> dict:
    search = owned_search(db, user, search_id)
    spec = view_spec_from_query(
        sort=clean_sort(sort),
        min_rating=min_rating,
        min_reviews=min_reviews,
        business_status=business_status,
        type_contains=type_contains,
        q=q,
        has_website=has_website,
        has_phone=has_phone,
        has_both=has_both,
        max_distance_km=max_distance_km,
    )
    paging = window(page, page_size)
    return _service(db).read(search, page=paging.page, page_size=paging.page_size, spec=spec)


@router.post("/search/{search_id}/rerun")
def rerun_search(
    search_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    search = owned_search(db, user, search_id)
    if user.role != "admin" and search.user_id != user.id:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Search not found.")
    return _service(db).rerun(user, search, client_ip(request))


@router.post("/bulk-search")
def bulk_search(
    body: BulkRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return run_bulk(db, user, body, client_ip(request), _service(db))
