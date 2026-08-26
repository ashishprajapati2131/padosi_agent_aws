from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from datetime import datetime
from fastapi_app.database import Base

class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    fullname = Column(String(191), nullable=False)
    email = Column(String(191), nullable=False, unique=True, index=True)
    mobile = Column(String(10), nullable=False)

    user = relationship("User", back_populates="agent")
    
    # Registration specific fields
    status = Column(String(191), default="incomplete")
    badge = Column(String(191), nullable=True, default="none")
    registration_step = Column(Integer, default=1)
    registration_draft = Column(JSON, nullable=True)
    
    # Other parsed Step 1 fields
    agent_pincode = Column(String(10), nullable=False)
    user_types = Column(JSON, nullable=True)
    insurance_companies = Column(JSON, nullable=True)
    experience_range = Column(String(191), nullable=True)
    client_base = Column(String(191), nullable=True)
    
    # Pricing, trial & referral fields mapping to database columns
    plan_type = Column(String(191), nullable=False, default="")
    trial_ends_at = Column(DateTime, nullable=True)
    upgrade_discount_percent = Column(Numeric(10, 2), nullable=True)
    referred_by_code = Column(String(191), nullable=True)
    referral_reward_type = Column(String(191), nullable=True)
    
    # Standard timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_primary_profile(self):
        try:
            return self.profile
        except Exception:
            return None

    # Relationships
    insurance_segments = relationship(
        "AgentInsuranceSegment", 
        back_populates="agent", 
        cascade="all, delete-orphan"
    )
    profile = relationship(
        "AgentProfile",
        backref="agent",
        uselist=False,
        cascade="all, delete-orphan"
    )
    subscriptions = relationship(
        "AgentSubscription",
        backref="agent",
        cascade="all, delete-orphan"
    )
    serviceable_cities = relationship(
        "AgentServiceableCity",
        backref="agent",
        cascade="all, delete-orphan"
    )
    portfolios = relationship(
        "AgentPortfolio",
        backref="agent",
        cascade="all, delete-orphan"
    )
    lead_preferences = relationship(
        "AgentLeadPreference",
        backref="agent",
        uselist=False,
        cascade="all, delete-orphan"
    )
    family_licenses = relationship(
        "AgentFamilyLicense",
        back_populates="agent",
        cascade="all, delete-orphan"
    )
    performance_stats = relationship(
        "AgentPerformanceStat",
        back_populates="agent",
        uselist=False,
        cascade="all, delete-orphan"
    )
    achievement_photos = relationship(
        "AgentAchievementPhoto",
        back_populates="agent",
        cascade="all, delete-orphan"
    )
    career_timelines = relationship(
        "AgentCareerTimeline",
        back_populates="agent",
        cascade="all, delete-orphan"
    )
    service_pincodes = relationship(
        "AgentServicePincode",
        back_populates="agent",
        cascade="all, delete-orphan"
    )
    product_expertise = relationship(
        "AgentProductExpertise",
        back_populates="agent",
        cascade="all, delete-orphan"
    )
    reviews = relationship(
        "AgentReview",
        back_populates="agent",
        cascade="all, delete-orphan"
    )
