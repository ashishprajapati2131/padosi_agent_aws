from sqlalchemy import Column, Integer, String, JSON, DateTime
from app.database import Base
from datetime import datetime, timezone

class ApiLog(Base):
    __tablename__ = "api_logs"

    id = Column(Integer, primary_key=True, index=True)
    service = Column(String(50), default="fastapi", index=True)
    request_url = Column(String(255))
    method = Column(String(10))
    payload = Column(JSON, nullable=True)
    response = Column(JSON, nullable=True)
    response_code = Column(Integer, index=True, nullable=True)
    ip_address = Column(String(39), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
