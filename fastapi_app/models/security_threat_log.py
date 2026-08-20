from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from fastapi_app.database import Base

class SecurityThreatLog(Base):
    __tablename__ = "security_threat_logs"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(191), index=True, nullable=False)
    event_type = Column(String(191), nullable=False)
    hacker_name = Column(String(191), nullable=True)
    hacker_email = Column(String(191), nullable=True)
    hacker_mobile = Column(String(191), nullable=True)
    location = Column(String(255), nullable=True)
    isp = Column(String(255), nullable=True)
    url = Column(Text, nullable=False)
    payload = Column(Text, nullable=True)
    user_agent = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
