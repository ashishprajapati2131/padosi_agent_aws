from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class AgentServicePincode(Base):
    __tablename__ = 'agent_service_pincodes'
    __table_args__ = (UniqueConstraint('agent_id', 'service_pincode', name='uq_agent_pincode'),)

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey('agents.id', ondelete='CASCADE'), nullable=False)
    service_pincode = Column(String(10), nullable=False)
    city_name = Column(String(150), nullable=False)
    selected_areas_json = Column(JSON, nullable=True)
    postal_data_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent = relationship("Agent", back_populates="service_pincodes")
