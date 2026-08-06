from pydantic import BaseModel
from typing import List, Optional

class SocialLinksSchema(BaseModel):
    linkedin: Optional[str] = None
    facebook: Optional[str] = None
    instagram: Optional[str] = None
    youtube: Optional[str] = None
    google_business: Optional[str] = None

class BadgeSchema(BaseModel):
    key: str
    label: str

class InsuranceSegmentSchema(BaseModel):
    key: str
    label: str

class TimelineSchema(BaseModel):
    year_month: str
    text: str

class PerformanceStatsSchema(BaseModel):
    clients_served: str
    claims_processed: str
    success_rate: str
    claims_settled: str
    response_time: str

class ServiceFeeSchema(BaseModel):
    label: str
    value: str

class ReviewSchema(BaseModel):
    reviewer_name: str
    reviewer_initial: str
    rating: int
    text: str
    date: str

class PublicProfileResponse(BaseModel):
    agent_id: int
    display_name: str
    agent_initial: str
    profile_photo_url: Optional[str] = None
    badges: List[BadgeSchema] = []
    career_highlights: str
    
    experience_years: str
    client_base: str
    languages: str
    
    insurance_segments: List[InsuranceSegmentSchema] = []
    
    average_rating: str
    review_count: int
    
    social_links: SocialLinksSchema
    
    career_timeline: List[TimelineSchema] = []
    certifications: List[str] = []
    achievements: List[str] = []
    
    performance_stats: PerformanceStatsSchema
    service_fees: List[ServiceFeeSchema] = []
    
    media_urls: List[str] = []
    
    reviews: List[ReviewSchema] = []
