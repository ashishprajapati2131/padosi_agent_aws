from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database.connection import get_db
from app.models import ApiUsageLog, Search, User
from app.services.retention import cleanup_expired

router = APIRouter(prefix="/admin", tags=["admin"])


def _day_key(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).date().isoformat()


def _series(counts: dict[str, int], days: int) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    points = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        points.append({"date": day, "count": int(counts.get(day, 0))})
    return points


@router.get("/stats")
def stats(db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> dict:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    total_users = db.query(func.count(User.id)).scalar() or 0
    total_searches = db.query(func.count(Search.id)).scalar() or 0
    searches_today = db.query(func.count(Search.id)).filter(Search.created_at >= start).scalar() or 0
    api_requests = db.query(func.count(ApiUsageLog.id)).scalar() or 0
    api_errors = db.query(func.count(ApiUsageLog.id)).filter(ApiUsageLog.success.is_(False)).scalar() or 0

    categories = (
        db.query(Search.category, func.count(Search.id))
        .group_by(Search.category)
        .order_by(func.count(Search.id).desc())
        .limit(8)
        .all()
    )
    locations = (
        db.query(Search.location_text, func.count(Search.id))
        .group_by(Search.location_text)
        .order_by(func.count(Search.id).desc())
        .limit(8)
        .all()
    )
    recent = db.query(Search).order_by(Search.created_at.desc()).limit(8).all()
    failed = (
        db.query(ApiUsageLog).filter(ApiUsageLog.success.is_(False)).order_by(ApiUsageLog.created_at.desc()).limit(8).all()
    )
    return {
        "total_users": int(total_users),
        "total_searches": int(total_searches),
        "searches_today": int(searches_today),
        "api_requests": int(api_requests),
        "api_errors": int(api_errors),
        "estimated_google_requests": int(api_requests),
        "top_categories": [{"name": name, "count": int(count)} for name, count in categories],
        "top_locations": [{"name": name, "count": int(count)} for name, count in locations],
        "recent_searches": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "query": row.query,
                "category": row.category,
                "location_text": row.location_text,
                "result_count": row.result_count,
                "status": row.status,
                "created_at": row.created_at,
            }
            for row in recent
        ],
        "failed_requests": [
            {
                "id": row.id,
                "endpoint": row.endpoint,
                "google_operation": row.google_operation,
                "error_type": row.error_type,
                "status_code": row.status_code,
                "created_at": row.created_at,
            }
            for row in failed
        ],
    }


@router.get("/api-usage")
def api_usage(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
    days: int = Query(30, ge=7, le=90),
) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    searches = db.query(Search).filter(Search.created_at >= since).all()
    errors = db.query(ApiUsageLog).filter(ApiUsageLog.success.is_(False), ApiUsageLog.created_at >= since).all()
    search_counts: dict[str, int] = {}
    for row in searches:
        key = _day_key(row.created_at)
        search_counts[key] = search_counts.get(key, 0) + 1
    error_counts: dict[str, int] = {}
    for row in errors:
        key = _day_key(row.created_at)
        error_counts[key] = error_counts.get(key, 0) + 1
    categories = (
        db.query(Search.category, func.count(Search.id))
        .filter(Search.created_at >= since)
        .group_by(Search.category)
        .order_by(func.count(Search.id).desc())
        .limit(8)
        .all()
    )
    locations = (
        db.query(Search.location_text, func.count(Search.id))
        .filter(Search.created_at >= since)
        .group_by(Search.location_text)
        .order_by(func.count(Search.id).desc())
        .limit(8)
        .all()
    )
    return {
        "daily_searches": _series(search_counts, days),
        "daily_errors": _series(error_counts, days),
        "categories": [{"name": name, "count": int(count)} for name, count in categories],
        "locations": [{"name": name, "count": int(count)} for name, count in locations],
    }


@router.post("/retention/cleanup")
def retention_cleanup(db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> dict:
    return cleanup_expired(db)
