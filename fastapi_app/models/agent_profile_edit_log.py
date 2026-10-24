from sqlalchemy import Column, Integer, BigInteger, String, JSON, DateTime
from datetime import datetime
from fastapi_app.database import Base

class AgentProfileEditLog(Base):
    """Mirror of Django apps.agents.AgentProfileEditLog (Django owns the table)."""
    __tablename__ = "agent_profile_edit_logs"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, index=True)
    agent_id = Column(Integer, nullable=False, index=True)
    edited_by = Column(String(50), nullable=False)
    edited_by_id = Column(Integer, nullable=True)
    step = Column(Integer, nullable=True)
    step_label = Column(String(255), nullable=True)
    changes = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    status_before = Column(String(50), nullable=True)
    status_after = Column(String(50), nullable=True)
    # Naive local time like Django (USE_TZ=False): get_edit_logs compares these to admin-written rows.
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
