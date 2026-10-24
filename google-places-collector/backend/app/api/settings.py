from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.config import get_settings
from app.models import User

router = APIRouter(tags=["settings"])


@router.get("/settings")
def public_settings(_user: User = Depends(get_current_user)) -> dict:
    settings = get_settings()
    return {
        "field_mode": settings.google_places_field_mode,
        "search_retention_days": settings.search_retention_days,
        "max_results_per_search": settings.max_results_per_search,
        "max_searches_per_minute": settings.max_searches_per_minute,
        "bulk_max_rows": settings.bulk_max_rows,
        "bulk_concurrency": settings.bulk_concurrency,
        "environment": settings.environment,
    }
