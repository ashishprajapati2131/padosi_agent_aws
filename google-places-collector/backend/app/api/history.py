from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.connection import get_db
from app.models import Export, Search, SearchResult, User
from app.services.presenters import search_dict
from app.utils.pagination import window

router = APIRouter(tags=["history"])


@router.get("/history")
def list_history(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    paging = window(page, page_size)
    query = db.query(Search).filter(Search.user_id == user.id).order_by(Search.created_at.desc(), Search.id.desc())
    total = query.count()
    rows = query.offset(paging.offset).limit(paging.page_size).all()
    return {
        "results": [search_dict(row) for row in rows],
        "page": paging.page,
        "page_size": paging.page_size,
        "total": total,
    }


@router.delete("/history/{search_id}", status_code=204)
def delete_history(
    search_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    search = db.get(Search, search_id)
    if search is None or search.user_id != user.id:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Search not found.")
    db.query(SearchResult).filter(SearchResult.search_id == search.id).delete(synchronize_session=False)
    db.query(Export).filter(Export.search_id == search.id).delete(synchronize_session=False)
    db.delete(search)
    db.commit()
