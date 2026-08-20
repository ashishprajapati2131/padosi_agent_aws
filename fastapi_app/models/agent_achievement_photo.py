from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from fastapi_app.database import Base
from sqlalchemy.sql import func

class AgentAchievementPhoto(Base):
    __tablename__ = "agent_achievement_photos"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    photo_path = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    agent = relationship("Agent", back_populates="achievement_photos")
