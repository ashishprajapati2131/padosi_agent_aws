from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Boolean
from datetime import datetime
from fastapi_app.database import Base

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(191), nullable=False, unique=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    
    agent_name = Column(String(191), nullable=True)
    agent_email = Column(String(191), nullable=True)
    agent_mobile = Column(String(191), nullable=True)
    agent_address = Column(String(255), nullable=True)
    agent_state = Column(String(191), nullable=True)
    
    plan_name = Column(String(191), nullable=True)
    plan_type = Column(String(191), nullable=True)
    
    base_amount = Column(Numeric(10, 2), nullable=False)
    gst_amount = Column(Numeric(10, 2), nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    discount_percent = Column(Numeric(10, 2), nullable=True)
    discount_folder = Column(String(191), nullable=True)
    promo_code = Column(String(191), nullable=True)
    
    razorpay_payment_id = Column(String(191), nullable=True)
    razorpay_order_id = Column(String(191), nullable=True)
    payment_status = Column(String(50), default="pending")
    pdf_path = Column(String(255), nullable=True)
    
    synced_to_sheet = Column(Boolean, default=False)
    synced_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
