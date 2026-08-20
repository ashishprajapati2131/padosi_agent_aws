from sqlalchemy import Column, Integer, String, Text, BigInteger, ForeignKey, DateTime
from datetime import datetime
from fastapi_app.database import Base

class AgentPortfolio(Base):
    """Maps agent_portfolios table (portfolio segment breakdown per agent)."""
    __tablename__ = "agent_portfolios"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)

    segment_type = Column(String(191), nullable=False)
    primary_companies = Column(Text, nullable=True)    # JSON array
    secondary_companies = Column(Text, nullable=True)  # JSON array

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
