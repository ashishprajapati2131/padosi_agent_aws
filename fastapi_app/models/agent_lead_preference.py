from sqlalchemy import Column, Integer, BigInteger, Boolean, String, Numeric, ForeignKey, DateTime
from datetime import datetime
from fastapi_app.database import Base

class AgentLeadPreference(Base):
    __tablename__ = "agent_lead_preferences"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    leads_new_business = Column(Boolean, default=False, nullable=False)
    leads_portfolio_analysis = Column(Boolean, default=False, nullable=False)
    portfolio_charging = Column(String(191), nullable=True)
    portfolio_fee = Column(Numeric(10, 2), nullable=True)
    leads_claims_support = Column(Boolean, default=False, nullable=False)
    claims_charging = Column(String(191), nullable=True)
    claims_fee_amount = Column(Numeric(10, 2), nullable=True)
    claims_percent = Column(Numeric(5, 2), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
