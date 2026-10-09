from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime
from fastapi_app.database import Base


class AppVersion(Base):
    """
    Mirror of the Django `app_versions` table (apps/admin_panel/models/app_version.py).
    One row per platform. Read by the mobile version-check endpoint.
    """
    __tablename__ = "app_versions"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(20), unique=True, index=True, nullable=False)
    latest_version = Column(String(20), nullable=False)
    min_supported_version = Column(String(20), nullable=False)
    force_update = Column(Boolean, default=False, nullable=False)
    update_message = Column(String(255), default="", nullable=True)
    store_url = Column(String(500), default="", nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
