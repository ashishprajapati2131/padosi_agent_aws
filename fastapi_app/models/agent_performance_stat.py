from sqlalchemy import Column, Integer, Numeric, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from fastapi_app.database import Base
from sqlalchemy.sql import func

class AgentPerformanceStat(Base):
    __tablename__ = "agent_performance_stats"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, unique=True)
    claims_processed = Column(Integer, default=0)
    claims_settled = Column(Integer, default=0)
    claims_amount = Column(Numeric(15, 2), default=0.0)
    success_rate = Column(Numeric(5, 2), default=0.0)
    response_time = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    agent = relationship("Agent", back_populates="performance_stats")
