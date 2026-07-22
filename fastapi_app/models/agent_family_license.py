from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship as orm_relationship
from app.database import Base
from sqlalchemy.sql import func

class AgentFamilyLicense(Base):
    __tablename__ = "agent_family_licenses"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    full_name = Column(String(255), nullable=False)
    relationship = Column(String(255), nullable=False)
    license_number = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    agent = orm_relationship("Agent", back_populates="family_licenses")
