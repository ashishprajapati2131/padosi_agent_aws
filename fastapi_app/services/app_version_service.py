from typing import Optional
from sqlalchemy.orm import Session

from fastapi_app.repositories.app_version_repository import AppVersionRepository
from fastapi_app.schemas.app_version import AppVersionResponse

VALID_PLATFORMS = {"android", "ios"}


def _version_tuple(v: Optional[str]):
    parts = []
    for p in (v or "").strip().split("."):
        try:
            parts.append(int(p))
        except (TypeError, ValueError):
            parts.append(0)
    return tuple(parts)


def _compare(a: Optional[str], b: Optional[str]) -> int:
    """Return -1 if a<b, 0 if equal, 1 if a>b (part-by-part)."""
    ta, tb = _version_tuple(a), _version_tuple(b)
    length = max(len(ta), len(tb))
    ta = ta + (0,) * (length - len(ta))
    tb = tb + (0,) * (length - len(tb))
    if ta < tb:
        return -1
    if ta > tb:
        return 1
    return 0


class AppVersionService:
    @staticmethod
    def check(db: Session, platform: str, current_version: Optional[str]) -> AppVersionResponse:
        platform = (platform or "").strip().lower()
        if platform not in VALID_PLATFORMS:
            platform = "android"

        row = AppVersionRepository(db).get_active_by_platform(platform)

        # No active config → never block the app; report no update.
        if not row:
            return AppVersionResponse(
                platform=platform,
                latest_version=current_version or "0.0.0",
                min_supported_version="0.0.0",
                current_version=current_version,
                update_available=False,
                update_required=False,
                force_update=False,
                update_message="",
                store_url="",
            )

        update_available = False
        update_required = False
        if current_version:
            update_available = _compare(current_version, row.latest_version) < 0
            below_min = _compare(current_version, row.min_supported_version) < 0
            update_required = bool(row.force_update and below_min)

        return AppVersionResponse(
            platform=platform,
            latest_version=row.latest_version,
            min_supported_version=row.min_supported_version,
            current_version=current_version,
            update_available=update_available,
            update_required=update_required,
            force_update=bool(row.force_update),
            update_message=row.update_message or "",
            store_url=row.store_url or "",
        )
