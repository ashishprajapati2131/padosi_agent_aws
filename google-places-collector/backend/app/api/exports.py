from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, owned_search
from app.database.connection import get_db
from app.models import Export, Place, SavedPlace, SearchResult, User
from app.schemas.place import ExportCreate
from app.services.export_service import place_export_dict, render_csv, render_xlsx
from app.services.presenters import StoredItem
from app.services.result_filters import FilterSpec, apply_filters, sort_items

router = APIRouter(tags=["exports"])

_MEDIA = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _format(value: str) -> str:
    fmt = (value or "").strip().lower()
    if fmt not in _MEDIA:
        raise HTTPException(status_code=422, detail="Export format must be csv or xlsx.")
    return fmt


def _rows_for_search(db: Session, user: User, search_id: int, place_ids: list[int] | None) -> tuple[list[dict], str]:
    search = owned_search(db, user, search_id)
    pairs = (
        db.query(SearchResult, Place)
        .join(Place, Place.id == SearchResult.place_id)
        .filter(SearchResult.search_id == search.id)
        .all()
    )
    items = [StoredItem(place, result) for result, place in pairs]
    ordered = sort_items(apply_filters(items, FilterSpec()), "position_asc")
    if place_ids:
        wanted = set(place_ids)
        ordered = [item for item in ordered if item.place.id in wanted]
        if not ordered:
            raise HTTPException(status_code=422, detail="None of the selected places are in this search.")
    return [place_export_dict(item.place) for item in ordered], search.field_mode


def _rows_for_saved(db: Session, user: User, place_ids: list[int] | None) -> list[dict]:
    saved = db.query(SavedPlace).filter(SavedPlace.user_id == user.id).order_by(SavedPlace.id.asc()).all()
    rows = []
    wanted = set(place_ids or [])
    for item in saved:
        if wanted and item.place_id not in wanted:
            continue
        place = db.get(Place, item.place_id)
        if place is not None:
            rows.append(place_export_dict(place))
    if place_ids and not rows:
        raise HTTPException(status_code=422, detail="None of the selected places are saved.")
    return rows


def _file_response(export: Export, payload: bytes, fmt: str, name: str) -> Response:
    return Response(
        content=payload,
        media_type=_MEDIA[fmt],
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Export-Id": str(export.id),
        },
    )


@router.post("/exports")
def create_export(
    body: ExportCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    fmt = _format(body.format)
    field_mode = "allowlist"
    if body.search_id is not None:
        rows, field_mode = _rows_for_search(db, user, body.search_id, body.place_ids)
        filename = f"places-search-{body.search_id}.{fmt}"
    elif body.saved:
        rows = _rows_for_saved(db, user, body.place_ids)
        filename = f"places-saved.{fmt}"
    else:
        raise HTTPException(status_code=422, detail="Choose a search or saved places to export.")
    payload = render_csv(rows) if fmt == "csv" else render_xlsx(rows)
    export = Export(
        user_id=user.id,
        search_id=body.search_id,
        format=fmt,
        field_mode=field_mode,
        row_count=len(rows),
    )
    db.add(export)
    db.commit()
    db.refresh(export)
    return _file_response(export, payload, fmt, filename)


@router.get("/exports")
def list_exports(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    size = min(max(page_size, 1), 100)
    current = max(page, 1)
    query = db.query(Export).filter(Export.user_id == user.id).order_by(Export.created_at.desc(), Export.id.desc())
    total = query.count()
    rows = query.offset((current - 1) * size).limit(size).all()
    return {
        "results": [
            {
                "id": row.id,
                "search_id": row.search_id,
                "format": row.format,
                "field_mode": row.field_mode,
                "row_count": row.row_count,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "page": current,
        "page_size": size,
        "total": total,
    }


@router.get("/exports/{export_id}")
def download_export(
    export_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    export = db.get(Export, export_id)
    if export is None or export.user_id != user.id:
        raise HTTPException(status_code=404, detail="Export not found.")
    fmt = _format(export.format)
    if export.search_id is not None:
        rows, _field_mode = _rows_for_search(db, user, export.search_id, None)
        filename = f"places-search-{export.search_id}.{fmt}"
    else:
        rows = _rows_for_saved(db, user, None)
        filename = f"places-saved.{fmt}"
    payload = render_csv(rows) if fmt == "csv" else render_xlsx(rows)
    return _file_response(export, payload, fmt, filename)
