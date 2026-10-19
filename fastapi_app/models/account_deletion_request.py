from sqlalchemy import Column, Integer, BigInteger, String, Text, Boolean, JSON, DateTime, Date
from datetime import datetime
from fastapi_app.database import Base


class AccountDeletionRequest(Base):
    __tablename__ = "account_deletion_requests"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    reference_id = Column(String(50), unique=True, nullable=False, index=True)
    identifier = Column(String(255), nullable=False, index=True)
    email = Column(String(254), nullable=False, default="")
    mobile = Column(String(20), nullable=False, default="")
    account_type = Column(String(50), nullable=False, default="agent")
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    verification_method = Column(String(30), nullable=False, default="otp_email")
    is_verified = Column(Boolean, nullable=False, default=False)
    reason = Column(Text, nullable=False, default="")
    rejection_reason = Column(Text, nullable=False, default="")
    scheduled_purge_date = Column(Date, nullable=True)
    admin_notes = Column(Text, nullable=False, default="")
    processed_by_admin_name = Column(String(150), nullable=False, default="")
    processed_at = Column(DateTime, nullable=True)
    data_retention_summary = Column(JSON, nullable=True)
    ip_address = Column(String(39), nullable=True)
    user_agent = Column(Text, nullable=False, default="")
    agent_id = Column(BigInteger, nullable=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    processed_by_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
