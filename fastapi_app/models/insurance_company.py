from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from app.database import Base

class InsuranceCompany(Base):
    __tablename__ = "insurance_companies"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(191), unique=True, nullable=False)
    name = Column(String(191), nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
