from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime

class AgentSummary(BaseModel):
    id: int
    fullname: str
    display_name: Optional[str] = None
    email: str
    mobile: Optional[str] = None
    status: str
    plan_type: Optional[str] = None
    photo_url: Optional[str] = None
    profile_slug: Optional[str] = None
    experience_range: Optional[str] = None
    languages: Optional[str] = None
    agency_name: Optional[str] = None

class SubscriptionInfo(BaseModel):
    plan_name: Optional[str] = None
    plan_type: Optional[str] = None
    status: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_active: bool = False

class TrialInfo(BaseModel):
    is_on_trial: bool
    trial_days_left: Optional[int] = None
    trial_expired: bool = False
    upgrade_discount_pct: int = 0
    starter_full_price: int = 0
    starter_discounted_price: int = 0
    professional_full_price: int = 0
    professional_discounted_price: int = 0

class LeadStats(BaseModel):
    total_leads: int
    monthly_leads: int
    new_leads: int
    contacted_leads: int
    follow_up_leads: int
    closed_leads: int
    active_leads: int
    conversion_rate: float

class PageViewStats(BaseModel):
    total_page_views: int
    monthly_visits: int

class PerformanceOverview(BaseModel):
    conversion_rate: float
    monthly_target: int
    total_page_views: int
    contact_requests: int
    monthly_visits: int

class RecentLead(BaseModel):
    id: int
    customer_name: Optional[str] = None
    customer_mobile: Optional[str] = None
    customer_email: Optional[str] = None
    customer_pincode: Optional[str] = None
    enquiry_requirements: Optional[str] = None
    interaction_type: str
    lead_status: str
    created_at: datetime

class ProfileCompletion(BaseModel):
    percentage: int
    has_address_and_languages: bool
    has_serviceable_cities: bool
    has_insurance_segments: bool
    has_portfolio: bool
    has_profile_photo: bool
    has_lead_preferences: bool

class TierInfo(BaseModel):
    min: int
    max: int
    reward: str
    label: str
    discount: int

class ReferralInfo(BaseModel):
    show_referral: bool
    referral_code: Optional[str] = None
    total_referrals: int = 0
    current_tier: Optional[TierInfo] = None
    next_tier: Optional[TierInfo] = None

class DashboardResponse(BaseModel):
    success: bool
    agent: AgentSummary
    subscription: SubscriptionInfo
    trial: TrialInfo
    performance: PerformanceOverview
    lead_stats: LeadStats
    recent_leads: List[RecentLead]
    profile_completion: ProfileCompletion
    insurance_segments: List[str]
    serviceable_cities: List[str]
    referral: ReferralInfo
