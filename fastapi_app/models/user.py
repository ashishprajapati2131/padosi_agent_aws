from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from fastapi_app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    fullname = Column(String(191), nullable=False)
    email = Column(String(191), nullable=False, unique=True, index=True)
    password = Column(String(191), nullable=False)
    role = Column(String(50), default="agent")
    status = Column(String(50), default="active")
    remember_token = Column(String(100), nullable=True)
    email_verified_at = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent = relationship("Agent", back_populates="user", uselist=False)
