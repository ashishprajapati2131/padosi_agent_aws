from sqlalchemy import Column, String, DateTime
from app.database import Base
from datetime import datetime

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    email = Column(String(191), primary_key=True, index=True)
    token = Column(String(191), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
