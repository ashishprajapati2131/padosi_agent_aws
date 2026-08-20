from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime
from fastapi_app.database import Base

class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(191), nullable=False)
    state = Column(String(191), nullable=True)
    slug = Column(String(191), unique=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
