from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from fastapi_app.database import get_db
from fastapi_app.schemas.app_version import AppVersionResponse
from fastapi_app.services.app_version_service import AppVersionService

router = APIRouter(
    prefix="/v1/app",
    tags=["App Version"],
)


@router.get("/version", response_model=AppVersionResponse)
def check_app_version(
    platform: str = Query("android", description="android or ios"),
    current_version: Optional[str] = Query(None, description="Installed app version, e.g. 1.2.0"),
    db: Session = Depends(get_db),
):
    """
    Public version-check for the mobile app (module #16 — Force-Update & App Version Control).

    The app calls this on launch. It returns whether an update is available (soft prompt)
    or required (hard block), plus the store URL and message to show.
    """
    return AppVersionService.check(db, platform, current_version)
