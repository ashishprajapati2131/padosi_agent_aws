"""Delete aged searches and results. Places that are still saved are kept.

There is no scheduler in this app. Call cleanup_expired from the admin API
and schedule that call in production (see docs/compliance.md).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Export, Place, SavedPlace, Search, SearchResult


def cleanup_expired(db: Session, *, now: datetime | None = None) -> dict:
    moment = now or datetime.now(timezone.utc)
    cutoff = moment - timedelta(days=get_settings().search_retention_days)
    old_ids = [row.id for row in db.query(Search.id).filter(Search.created_at < cutoff).all()]
    deleted_results = 0
    deleted_searches = 0
    if old_ids:
        db.query(Export).filter(Export.search_id.in_(old_ids)).delete(synchronize_session=False)
        deleted_results = (
            db.query(SearchResult)
            .filter(SearchResult.search_id.in_(old_ids))
            .delete(synchronize_session=False)
        )
        deleted_searches = db.query(Search).filter(Search.id.in_(old_ids)).delete(synchronize_session=False)

    saved_ids = db.query(SavedPlace.place_id)
    referenced_ids = db.query(SearchResult.place_id)
    deleted_orphans = (
        db.query(Place)
        .filter(~Place.id.in_(saved_ids), ~Place.id.in_(referenced_ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return {
        "deleted_searches": int(deleted_searches or 0),
        "deleted_results": int(deleted_results or 0),
        "deleted_orphan_places": int(deleted_orphans or 0),
        "retention_days": get_settings().search_retention_days,
        "cutoff": cutoff.isoformat(),
    }
