from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON
from datetime import datetime

from fastapi_app.database import Base


class AgentPlanOffer(Base):
    """Scratch and social-follow state for one agent's mobile plan prices."""

    __tablename__ = "agent_plan_offers"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    scratched_starter = Column(Boolean, nullable=False, default=False)
    scratched_professional = Column(Boolean, nullable=False, default=False)
    followed_platforms = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
