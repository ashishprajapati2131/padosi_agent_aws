from sqlalchemy import Column, Integer, BigInteger, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from fastapi_app.database import Base

class AgentServiceableCity(Base):
    """Pivot table: agent_serviceable_cities"""
    __tablename__ = "agent_serviceable_cities"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    city_id = Column(Integer, ForeignKey("cities.id", ondelete="CASCADE"), nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    city = relationship("City")
