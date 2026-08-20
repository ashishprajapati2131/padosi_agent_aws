from sqlalchemy import Column, Integer, String, Text, DateTime, BigInteger, ForeignKey, Index
from datetime import datetime
from fastapi_app.database import Base

class AgentLead(Base):
    __tablename__ = "agent_leads"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)

    customer_name = Column(String(191), nullable=True)
    customer_email = Column(String(191), nullable=True)
    customer_mobile = Column(String(191), nullable=True)
    customer_pincode = Column(String(20), nullable=True)

    interaction_type = Column(String(191), nullable=False, default="direct")
    lead_status = Column(String(191), nullable=False, default="new")
    service_type = Column(String(191), nullable=True)
    insurance_type = Column(String(191), nullable=True)
    insurance_company = Column(String(191), nullable=True)
    enquiry_requirements = Column(Text, nullable=True)
    source_page = Column(String(191), nullable=True)
    ip_address = Column(String(45), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_ip_created", "ip_address", "created_at"),
    )
