import json
from typing import Any, Optional
from sqlalchemy.orm import Session
from app.models.site_setting import SiteSetting

class SiteSettingRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_key(self, key: str) -> Optional[SiteSetting]:
        return self.db.query(SiteSetting).filter(SiteSetting.key == key).first()

    def get_json_value(self, key: str, default: Any = None) -> Any:
        setting = self.get_by_key(key)
        if setting and setting.value:
            try:
                return json.loads(setting.value)
            except json.JSONDecodeError:
                return default
        return default
