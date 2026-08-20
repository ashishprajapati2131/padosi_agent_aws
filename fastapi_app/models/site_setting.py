from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from fastapi_app.database import Base

class SiteSetting(Base):
    __tablename__ = "site_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(191), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=True)
    group = Column(String(191), nullable=False, default="general")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
