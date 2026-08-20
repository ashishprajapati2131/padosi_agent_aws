from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from fastapi_app.database import Base

class BlockedIp(Base):
    __tablename__ = "blocked_ips"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(191), unique=True, index=True, nullable=False)
    reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
