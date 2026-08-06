from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import date

class SubscriptionSchema(BaseModel):
    selected_plan: Optional[str] = ""

class InsuranceSegmentSchema(BaseModel):
    segment_type: str

class ProductExpertiseSchema(BaseModel):
    segment_type: Optional[str] = ""
    product_name: str
    expertise_level: int = 1
    is_custom: bool = False

class ServicePincodeSchema(BaseModel):
    pincode: str
    city_name: str
    selected_areas: List[str] = []
    postal_data: List[Dict[str, Any]] = []

class FamilyLicenseSchema(BaseModel):
    full_name: Optional[str] = ""
    relationship: str
    license_number: Optional[str] = ""
    member_name: Optional[str] = ""
    license_type: Optional[str] = ""

class PerformanceStatSchema(BaseModel):
    claims_processed: int = 0
    claims_settled: int = 0
    claims_amount: float = 0.0
    success_rate: Optional[float] = 0.0
    response_time: Optional[str] = "2"

class PortfolioSchema(BaseModel):
    segment_type: str
    primary_companies: Dict[str, Any] = {}
    secondary_companies: Dict[str, Any] = {}

class CareerTimelineSchema(BaseModel):
    month: Optional[str] = ""
    year: Any
    type: str = "Career Event"
    event_text: Optional[str] = ""
    title: Optional[str] = ""

class AchievementPhotoSchema(BaseModel):
    id: Optional[int] = 0
    photo_url: str

class LeadPreferenceSchema(BaseModel):
    leads_new_business: bool = True
    leads_portfolio_analysis: bool = True
    portfolio_charging: str = "free"
    portfolio_fee: float = 0.0
    leads_claims_support: bool = True
    claims_charging: str = "free"
    claims_fee_amount: float = 0.0
    claims_percent: Optional[float] = 0.0

class AgentSchema(BaseModel):
    id: int
    status: str
    badge: Optional[str] = ""
    fullname: str
    email: str
    mobile: str
    experience_range: Optional[str] = ""
    client_base: Optional[str] = ""
    user_types: List[str] = []
    activeSubscription: Optional[SubscriptionSchema] = None
    insuranceSegments: List[InsuranceSegmentSchema] = []
    productExpertise: List[ProductExpertiseSchema] = []
    serviceableCities: List[str] = []
    familyLicenses: List[FamilyLicenseSchema] = []
    performanceStats: PerformanceStatSchema
    portfolios: List[PortfolioSchema] = []
    careerTimelines: List[CareerTimelineSchema] = []
    achievementPhotos: List[AchievementPhotoSchema] = []
    leadPreferences: Optional[LeadPreferenceSchema] = None

class SocialLinksSchema(BaseModel):
    google_business: Optional[str] = ""
    linkedin_url: Optional[str] = ""
    instagram_url: Optional[str] = ""
    facebook_url: Optional[str] = ""
    youtube_url: Optional[str] = ""

class ProfileSchema(BaseModel):
    profile_photo_url: Optional[str] = None
    display_name: Optional[str] = ""
    whatsapp: Optional[str] = ""
    languages: Optional[str] = ""
    address: Optional[str] = ""
    pan_number: Optional[str] = ""
    license_number: Optional[str] = ""
    license_valid_till: Optional[date] = None
    arn_number: Optional[str] = ""
    euin_number: Optional[str] = ""
    investment_valid_till: Optional[date] = None
    investment_types: List[str] = []
    agency_name: Optional[str] = ""
    office_address: Optional[str] = ""
    service_pincodes: List[ServicePincodeSchema] = []
    has_pos_license: bool = False
    career_highlights: Optional[str] = ""
    website: Optional[str] = ""
    social_links: SocialLinksSchema
    
    agent_show_experience: bool = True
    agent_show_claims_stats: bool = True
    agent_show_client_base: bool = True
    agent_show_ratings: bool = True
    agent_show_reviews: bool = True
    agent_show_certificates: bool = True
    agent_show_achievements: bool = True
    agent_show_social_media: bool = True
    agent_show_languages: bool = True
    agent_show_gallery: bool = True
    agent_show_contact_info: bool = True

class AgentProfileResponse(BaseModel):
    agent: AgentSchema
    profile: ProfileSchema

    class Config:
        from_attributes = True

class AgentUpdateSchema(BaseModel):
    fullname: str
    email: str
    mobile: str
    badge: Optional[str] = ""
    experience_range: Optional[str] = ""
    client_base: Optional[str] = ""
    user_types: List[str] = []
    insuranceSegments: List[InsuranceSegmentSchema] = []
    productExpertise: List[ProductExpertiseSchema] = []
    familyLicenses: List[FamilyLicenseSchema] = []
    performanceStats: PerformanceStatSchema
    portfolios: List[PortfolioSchema] = []
    careerTimelines: List[CareerTimelineSchema] = []
    achievementPhotos: List[AchievementPhotoSchema] = []
    leadPreferences: Optional[LeadPreferenceSchema] = None

class ProfileUpdateSchema(BaseModel):
    profile_photo_url: Optional[str] = None
    display_name: Optional[str] = ""
    whatsapp: Optional[str] = ""
    languages: str
    address: str
    pan_number: Optional[str] = ""
    license_number: Optional[str] = ""
    license_valid_till: Optional[date] = None
    arn_number: Optional[str] = ""
    euin_number: Optional[str] = ""
    investment_valid_till: Optional[date] = None
    investment_types: List[str] = []
    agency_name: Optional[str] = ""
    office_address: Optional[str] = ""
    service_pincodes: List[ServicePincodeSchema] = []
    has_pos_license: bool = False
    career_highlights: Optional[str] = ""
    website: Optional[str] = ""
    social_links: SocialLinksSchema
    
    agent_show_experience: bool = True
    agent_show_claims_stats: bool = True
    agent_show_client_base: bool = True
    agent_show_ratings: bool = True
    agent_show_reviews: bool = True
    agent_show_certificates: bool = True
    agent_show_achievements: bool = True
    agent_show_social_media: bool = True
    agent_show_languages: bool = True
    agent_show_gallery: bool = True
    agent_show_contact_info: bool = True

class AgentProfileUpdateRequest(BaseModel):
    agent: AgentUpdateSchema
    profile: ProfileUpdateSchema
