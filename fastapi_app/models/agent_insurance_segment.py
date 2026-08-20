from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime
from fastapi_app.database import Base

class AgentInsuranceSegment(Base):
    __tablename__ = "agent_insurance_segments"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    segment_type = Column(String(191), nullable=False)
    
    # Standard timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    agent = relationship("Agent", back_populates="insurance_segments")
