"""Confirmed bulk search. Stops on quota and auth errors instead of burning the batch."""

from __future__ import annotations

import csv
import io

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User
from app.schemas.search import BulkRequest, BulkRow, SearchCreate
from app.services.errors import (
    FATAL_GOOGLE_TYPES,
    AppError,
    GoogleServiceError,
    InputValidationError,
)
from app.services.rate_limit import limiter
from app.services.search_service import SearchService
from app.utils.logger import log_event


def parse_csv_rows(csv_text: str) -> list[BulkRow]:
    if len(csv_text) > 100_000:
        raise InputValidationError("That CSV is too large.")
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise InputValidationError("CSV must include category and location columns.")
    fields = {name.strip().lower(): name for name in reader.fieldnames if name}
    if "category" not in fields or "location" not in fields:
        raise InputValidationError("CSV must include category and location columns.")
    rows: list[BulkRow] = []
    for raw in reader:
        category = (raw.get(fields["category"]) or "").strip()
        location = (raw.get(fields["location"]) or "").strip()
        if not category and not location:
            continue
        radius = None
        if "radius" in fields:
            radius_text = (raw.get(fields["radius"]) or "").strip()
            if radius_text:
                try:
                    radius = float(radius_text)
                except ValueError as exc:
                    raise InputValidationError("Radius must be a number of kilometers.") from exc
        rows.append(BulkRow(category=category, location=location, radius_km=radius))
    return rows


def resolve_rows(body: BulkRequest) -> list[BulkRow]:
    if body.rows:
        return list(body.rows)
    if body.csv_text and body.csv_text.strip():
        return parse_csv_rows(body.csv_text)
    raise InputValidationError("Add at least one row with category and location.")


def run_bulk(db: Session, user: User, body: BulkRequest, client_ip: str, service: SearchService) -> dict:
    rows = resolve_rows(body)
    settings = get_settings()
    if not rows:
        raise InputValidationError("Add at least one row with category and location.")
    if len(rows) > settings.bulk_max_rows:
        raise InputValidationError(f"Bulk search accepts at most {settings.bulk_max_rows} rows.")
    message = f"You are about to perform {len(rows)} searches."
    if not body.confirm:
        return {
            "confirm_required": True,
            "search_count": len(rows),
            "message": message,
            "stopped": False,
            "stop_reason": None,
            "failed_row": None,
            "results": [
                {
                    "row": index,
                    "category": row.category,
                    "location": row.location,
                    "radius_km": row.radius_km if row.radius_km is not None else body_radius(body),
                }
                for index, row in enumerate(rows, start=1)
            ],
        }

    workers = min(settings.bulk_concurrency, 3)
    if workers != 1:
        log_event("info", "bulk_concurrency", workers=workers)
    limiter.reserve_search(user.id, client_ip, cost=len(rows))

    results = []
    stopped = False
    stop_reason = None
    failed_row = None
    for index, row in enumerate(rows, start=1):
        payload = SearchCreate(
            category=row.category,
            location=row.location,
            radius_km=row.radius_km if row.radius_km is not None else body_radius(body),
            keyword=body.keyword,
            max_results=body.max_results,
            language=body.language,
            search_mode=body.search_mode,
            min_rating=body.min_rating,
            min_reviews=body.min_reviews,
            business_status=body.business_status,
            type_contains=body.type_contains,
            has_website=body.has_website,
            has_phone=body.has_phone,
            has_both=body.has_both,
            max_distance_km=body.max_distance_km,
            sort=body.sort,
        )
        try:
            # The batch already reserved the rate-limit budget.
            outcome = service.execute(user, payload, client_ip, charge_rate_limit=False)
            search = outcome["search"]
            results.append(
                {
                    "row": index,
                    "category": row.category,
                    "location": row.location,
                    "search_id": search["id"] if isinstance(search, dict) else search.id,
                    "result_count": search["result_count"] if isinstance(search, dict) else search.result_count,
                    "status": "completed",
                    "error": None,
                }
            )
        except GoogleServiceError as exc:
            results.append(_failed(index, row, exc))
            if exc.error_type in FATAL_GOOGLE_TYPES:
                stopped = True
                stop_reason = exc.message
                failed_row = index
                break
        except AppError as exc:
            results.append(_failed(index, row, exc))
        except Exception:
            log_event("error", "bulk_row_failed", error_type="server_error", row=index)
            results.append(
                {
                    "row": index,
                    "category": row.category,
                    "location": row.location,
                    "search_id": None,
                    "result_count": 0,
                    "status": "failed",
                    "error": "This row could not be searched. Please try again.",
                }
            )
    completed = sum(1 for item in results if item["status"] == "completed")
    summary = message
    if stopped:
        summary = f"Stopped after row {failed_row}. {completed} search{'es' if completed != 1 else ''} completed."
    return {
        "confirm_required": False,
        "search_count": len(rows),
        "message": summary,
        "stopped": stopped,
        "stop_reason": stop_reason,
        "failed_row": failed_row,
        "results": results,
    }


def body_radius(body: BulkRequest) -> float:
    return 5.0


def _failed(index: int, row: BulkRow, exc: AppError) -> dict:
    return {
        "row": index,
        "category": row.category,
        "location": row.location,
        "search_id": exc.search_id,
        "result_count": 0,
        "status": "failed",
        "error": exc.message,
    }
