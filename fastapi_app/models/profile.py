from sqlalchemy import Column, Integer, String, Text, JSON, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class AgentProfile(Base):
    __tablename__ = "agent_profiles"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, unique=True)
    slug = Column(String(191), nullable=False, unique=True, index=True)
    profile_photo_path = Column(String(191), nullable=True)
    display_name = Column(String(191), nullable=True)
    whatsapp = Column(String(191), nullable=True)
    languages = Column(Text, nullable=True)  # Or JSON
    address = Column(Text, nullable=True)
    state = Column(String(191), nullable=True)
    pan_number = Column(String(191), nullable=True)
    license_number = Column(String(191), nullable=True)
    software_name = Column(String(191), nullable=True)
    portfolio_breakdown = Column(JSON, nullable=True)
    desired_services = Column(JSON, nullable=True)
    agency_name = Column(String(191), nullable=True)
    office_address = Column(Text, nullable=True)
    service_pincodes = Column(JSON, nullable=True)
    experience_years = Column(String(191), nullable=True)
    has_pos_license = Column(Boolean, default=False)
    website_url = Column(String(191), nullable=True)
    social_links = Column(JSON, nullable=True)
    career_highlights = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
