from typing import Optional
from sqlalchemy.orm import Session
from fastapi_app.models.app_version import AppVersion


class AppVersionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_active_by_platform(self, platform: str) -> Optional[AppVersion]:
        return (
            self.db.query(AppVersion)
            .filter(AppVersion.platform == platform, AppVersion.is_active == True)  # noqa: E712
            .first()
        )
