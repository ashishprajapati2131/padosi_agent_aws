from sqlalchemy import Column, Integer, String, Text, JSON, Boolean, ForeignKey, DateTime, Numeric, BigInteger, Date
from datetime import datetime
from app.database import Base

class AgentProfile(Base):
    __tablename__ = "agent_profiles"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    profile_photo_path = Column(String(191), nullable=True)
    display_name = Column(String(191), nullable=True)
    slug = Column(String(191), unique=True, nullable=True, index=True)
    whatsapp = Column(String(191), nullable=True)
    languages = Column(Text, nullable=True)
    address = Column(Text, nullable=True)
    state = Column(String(191), nullable=True)
    
    pan_number = Column(String(191), nullable=True)
    license_number = Column(String(191), nullable=True)
    license_valid_till = Column(Date, nullable=True)
    arn_number = Column(String(191), nullable=True)
    euin_number = Column(String(191), nullable=True)
    investment_valid_till = Column(Date, nullable=True)
    investment_types = Column(JSON, nullable=True)
    software_name = Column(String(191), nullable=True)
    
    portfolio_breakdown = Column(JSON, nullable=True)
    desired_services = Column(JSON, nullable=True)
    
    agency_name = Column(String(191), nullable=True)
    office_address = Column(Text, nullable=True)
    service_pincodes = Column(JSON, nullable=True)
    
    latitude = Column(Numeric(10, 8), nullable=True, index=True)
    longitude = Column(Numeric(11, 8), nullable=True)
    experience_years = Column(String(191), nullable=True)
    has_pos_license = Column(Boolean, default=False, nullable=False)
    
    website_url = Column(String(191), nullable=True)
    social_links = Column(JSON, nullable=True)
    career_highlights = Column(Text, nullable=True)
    
    irdai_license_doc = Column(String(255), nullable=True)
    amfi_license_doc = Column(String(255), nullable=True)
    
    is_profile_visible = Column(Boolean, default=True, nullable=False)
    show_certificates = Column(Boolean, default=True, nullable=False)
    show_achievements = Column(Boolean, default=True, nullable=False)
    show_reviews = Column(Boolean, default=True, nullable=False)
    
    agent_show_experience = Column(Boolean, default=True, nullable=False)
    agent_show_claims_stats = Column(Boolean, default=True, nullable=False)
    agent_show_client_base = Column(Boolean, default=True, nullable=False)
    agent_show_ratings = Column(Boolean, default=True, nullable=False)
    agent_show_reviews = Column(Boolean, default=True, nullable=False)
    agent_show_certificates = Column(Boolean, default=True, nullable=False)
    agent_show_achievements = Column(Boolean, default=True, nullable=False)
    agent_show_social_media = Column(Boolean, default=True, nullable=False)
    agent_show_languages = Column(Boolean, default=True, nullable=False)
    agent_show_gallery = Column(Boolean, default=True, nullable=False)
    agent_show_contact_info = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
