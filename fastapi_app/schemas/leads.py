from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class LeadDetail(BaseModel):
    id: int
    agent_id: int
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_mobile: Optional[str] = None
    customer_pincode: Optional[str] = None
    interaction_type: str
    lead_status: str
    service_type: Optional[str] = None
    insurance_type: Optional[str] = None
    insurance_company: Optional[str] = None
    enquiry_requirements: Optional[str] = None
    source_page: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class LeadsListResponse(BaseModel):
    success: bool
    total: int
    page: int
    page_size: int
    leads: List[LeadDetail]
    is_locked: bool = False
    unlock_hint: Optional[str] = None

class LeadStatusUpdate(BaseModel):
    status: str = Field(..., description="The status of the lead: new, contacted, follow_up, closed")

class CaptureLeadRequest(BaseModel):
    customer_name: str = Field(..., min_length=2)
    customer_mobile: str = Field(..., pattern=r'^\d{10}$')
    customer_email: Optional[str] = None
    customer_pincode: Optional[str] = None
    insurance_type: Optional[str] = None
    insurance_company: Optional[str] = None
    enquiry_requirements: Optional[str] = None
    interaction_type: str = "manual"

class LeadPreferencesRequest(BaseModel):
    leads_new_business: bool = True
    leads_portfolio_analysis: bool = True
    portfolio_charging: str = "free"
    portfolio_fee: float = 0.0
    leads_claims_support: bool = True
    claims_charging: str = "free"
    claims_fee_amount: float = 0.0
    claims_percent: Optional[float] = 0.0

class LeadPreferencesResponse(BaseModel):
    success: bool
    data: Dict[str, Any]
    message: Optional[str] = None
