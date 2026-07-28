from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class FindAgentsRequest(BaseModel):
    pincode: Optional[str] = Field(None, description="6-digit Indian Pincode", example="380015")
    location: Optional[str] = Field(None, description="City, State, or Area search string", example="Satellite, Ahmedabad")
    lat: Optional[float] = Field(None, description="User Latitude", example=23.0200)
    lng: Optional[float] = Field(None, description="User Longitude", example=72.5100)

    service_types: Optional[List[str]] = Field(
        default=[],
        alias="ServiceType",
        description="List of service types: New Policy, Claim Assistance, Policy Review, etc."
    )
    insurance_types: Optional[List[str]] = Field(
        default=[],
        alias="InsuranceType",
        description="List of insurance types: Health Insurance, Life Insurance, Motor Insurance, SME Insurance, etc."
    )
    insurance_companies: Optional[List[str]] = Field(
        default=[],
        alias="InsuranceCompany",
        description="Selected insurance companies"
    )
    claim_insurance_company: Optional[str] = Field(
        None,
        alias="ClaimInsuranceCompany",
        description="Company name for claim support lookup"
    )
    complaint_type: Optional[str] = Field(
        None,
        alias="ComplaintType",
        description="Complaint category for claim filter"
    )

    search: Optional[str] = Field(None, description="Keyword search for agent name, city, state")
    sort_by: Optional[str] = Field("match", description="Sort option: distance | match | rating | experience")

    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(10, ge=1, le=100, description="Number of agents per page")

    class Config:
        populate_by_name = True


class RecognitionBadge(BaseModel):
    class_name: str
    icon: str
    label: str


class AgentCardSchema(BaseModel):
    id: int
    display_name: str
    fullname: str
    profile_photo_url: str
    experience_years: int
    experience_range: str
    client_base: str
    formatted_client_base: str
    badge: str
    badges: List[RecognitionBadge]
    profession: Optional[str] = "LIC Agent"
    average_rating: float
    review_count: int
    star_rating_list: List[str]
    claims_processed: int
    formatted_claims_processed: str
    claims_amount: float
    formatted_claims_amount: str
    distance_km: Optional[float] = None
    has_distance: bool
    formatted_distance: str
    padosi_smart_rank: float
    match_percent: int
    match_color_class: str
    insurance_segments: List[str]
    agent_city_display: str
    agent_slug: str
    mobile: str
    whatsapp_raw: str
    whatsapp_digits: str
    is_approved_by_admin: bool
    is_verified_agent: bool
    is_trusted: bool


class PaginationMeta(BaseModel):
    total_records: int
    current_page: int
    total_pages: int
    page_size: int
    has_next: bool
    has_previous: bool
    next_page_number: Optional[int] = None
    previous_page_number: Optional[int] = None


class FindAgentsResponse(BaseModel):
    success: bool
    message: str
    detected_area: str
    invalid_pincode: bool
    sort_by: str
    max_smart_rank: float
    pagination: PaginationMeta
    filters_applied: Dict[str, Any]
    agents: List[AgentCardSchema]
