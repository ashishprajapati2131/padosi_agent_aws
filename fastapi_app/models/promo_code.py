from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, Text
from datetime import datetime
from app.database import Base

class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(191), nullable=False, unique=True, index=True)
    discount_type = Column(String(50), nullable=False, default="percentage")  # percentage or fixed
    discount_value = Column(Numeric(10, 2), nullable=False)
    is_free_trial = Column(Boolean, default=False)
    trial_plan_name = Column(String(191), nullable=True)
    trial_duration_days = Column(Integer, nullable=True)
    trial_price_override = Column(Numeric(10, 2), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    max_uses = Column(Integer, nullable=True)
    times_used = Column(Integer, default=0)
    applicable_plan = Column(String(255), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def is_valid(self) -> bool:
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        if self.max_uses and self.times_used >= self.max_uses:
            return False
        return True

    def calculate_discount(self, base_price: float) -> float:
        if self.discount_type == "percentage":
            return round((float(self.discount_value) / 100.0) * base_price, 2)
        elif self.discount_type in ["fixed", "flat", "amount"]:
            return min(float(self.discount_value), base_price)
        return 0.0

    def is_free_trial_code(self) -> bool:
        return bool(self.is_free_trial) or "trial" in self.code.lower() or self.trial_duration_days is not None
