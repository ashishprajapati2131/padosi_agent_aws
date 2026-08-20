from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from fastapi_app.database import Base

class AgentSubscription(Base):
    __tablename__ = "agent_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    selected_plan = Column(String(191), nullable=False)
    promo_code = Column(String(191), nullable=True)
    registration_amount = Column(Numeric(10, 2), nullable=False)
    razorpay_order_id = Column(String(191), nullable=True, index=True)
    razorpay_payment_id = Column(String(191), nullable=True)
    razorpay_signature = Column(String(191), nullable=True)
    payment_status = Column(String(50), default="pending")
    status = Column(String(50), default="inactive")
    starts_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
