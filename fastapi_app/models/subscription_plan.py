from sqlalchemy import Column, Integer, String, Text, Boolean, Numeric, DateTime
from datetime import datetime
from fastapi_app.database import Base


class SubscriptionPlan(Base):
    """
    SQLAlchemy model for subscription_plans table.
    Mirrors Django apps.agents.models.SubscriptionPlan.
    """
    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    slug = Column(String(50), unique=True, nullable=True, index=True)
    description = Column(Text, default="")
    color_theme = Column(String(50), default="starter-theme")
    badge_text = Column(String(50), nullable=True)
    sort_order = Column(Integer, default=0)

    html_code = Column(Text, default="")
    actual_price = Column(Numeric(10, 2), default=0.00)
    discounted_price = Column(Numeric(10, 2), default=0.00)

    # Feature toggles
    show_profile_section = Column(Boolean, default=True)
    show_agent_certificate = Column(Boolean, default=True)
    show_career_timeline = Column(Boolean, default=True)
    show_professional_bio = Column(Boolean, default=True)
    show_social_media = Column(Boolean, default=True)
    show_new_business_leads = Column(Boolean, default=True)
    show_portfolio = Column(Boolean, default=True)
    show_claim_support = Column(Boolean, default=True)
    show_companies = Column(Boolean, default=True)
    show_achievement = Column(Boolean, default=True)
    show_lead_status = Column(Boolean, default=True)
    show_sales_insights = Column(Boolean, default=True)
    show_recent_leads = Column(Boolean, default=True)

    # Granular access control fields
    show_performance_stats = Column(Boolean, default=True)
    show_rank_boost_tips = Column(Boolean, default=True)
    show_view_public_profile_btn = Column(Boolean, default=True)
    show_edit_profile_full = Column(Boolean, default=True)
    show_edit_profile_basic = Column(Boolean, default=True)
    show_edit_profile_professional = Column(Boolean, default=True)
    show_edit_profile_portfolio = Column(Boolean, default=True)
    show_edit_profile_additional = Column(Boolean, default=True)
    show_review_management = Column(Boolean, default=True)
    is_listed_in_directory = Column(Boolean, default=True)
    premium_priority_support = Column(Boolean, default=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
