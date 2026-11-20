from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from fastapi_app.database import Base


class AgentReview(Base):
    __tablename__ = "agent_reviews"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(
        Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    reviewer_name = Column(String(191), nullable=True)
    reviewer_email = Column(String(191), nullable=True)
    reviewer_mobile = Column(String(20), nullable=True)
    rating = Column(Integer, default=5, nullable=False)
    review = Column(Text, nullable=True)

    # Matches Django AgentReview default (False). Writes still go through Django for create.
    is_approved = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent = relationship("Agent", back_populates="reviews")
    user = relationship("User", foreign_keys=[user_id])
