from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from fastapi_app.database import Base

class AgentProductExpertise(Base):
    __tablename__ = 'agent_product_expertise'

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey('agents.id', ondelete='CASCADE'), nullable=False)
    segment_type = Column(String(50), nullable=False)
    product_name = Column(String(150), nullable=False)
    expertise_level = Column(Integer, default=1)
    is_custom = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent = relationship("Agent", back_populates="product_expertise")
