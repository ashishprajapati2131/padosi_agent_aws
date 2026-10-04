from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from fastapi_app.database import Base

class ReferralCode(Base):
    __tablename__ = "referral_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(191), nullable=False, unique=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, unique=True)
    is_active = Column(Boolean, default=True)
    clicks = Column(Integer, default=0)
    total_referrals = Column(Integer, default=0)
    reward_claimed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def current_tier(self) -> dict:
        # Canonical tier table (matches Django ReferralCode.tiers()):
        # Tier 1:  5 paid conversions -> 25% discount
        # Tier 2: 10 paid conversions -> 50% discount
        # Tier 3: 15 paid conversions -> Professional's Plan @ ₹1
        ref_count = self.total_referrals
        if ref_count >= 15:
            return {"tier": 3, "discount": 100, "label": "Tier 3: Professional's Plan for ₹1"}
        elif ref_count >= 10:
            return {"tier": 2, "discount": 50, "label": "Tier 2: 50% Discount"}
        elif ref_count >= 5:
            return {"tier": 1, "discount": 25, "label": "Tier 1: 25% Discount"}
        return {"tier": 0, "discount": 0, "label": "No tier reached yet"}

    def next_tier(self) -> dict:
        ref_count = self.total_referrals
        if ref_count < 5:
            return {"tier": 1, "min": 5, "discount": 25, "label": "Tier 1"}
        elif ref_count < 10:
            return {"tier": 2, "min": 10, "discount": 50, "label": "Tier 2"}
        elif ref_count < 15:
            return {"tier": 3, "min": 15, "discount": 100, "label": "Tier 3"}
        return None
