from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ApiUsageLog


def record_usage(
    db: Session,
    *,
    user_id: int | None,
    endpoint: str,
    search_type: str,
    google_operation: str,
    success: bool,
    status_code: int | None,
    duration_ms: int,
    result_count: int,
    error_type: str | None = None,
) -> None:
    db.add(
        ApiUsageLog(
            user_id=user_id,
            endpoint=endpoint[:80],
            search_type=search_type[:32],
            google_operation=google_operation[:32],
            success=success,
            status_code=status_code,
            duration_ms=max(0, int(duration_ms)),
            result_count=max(0, int(result_count)),
            error_type=error_type[:64] if error_type else None,
        )
    )
