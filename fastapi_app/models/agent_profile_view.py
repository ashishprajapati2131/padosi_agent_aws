from sqlalchemy import Column, Integer, BigInteger, ForeignKey, Date
from datetime import datetime
from app.database import Base

class AgentProfileView(Base):
    __tablename__ = "agent_profile_views"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    view_date = Column(Date, nullable=False)
    view_count = Column(Integer, default=0, nullable=False)

    created_at = Column(Date, default=datetime.utcnow)
    updated_at = Column(Date, default=datetime.utcnow)
