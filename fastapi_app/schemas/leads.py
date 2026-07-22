from pydantic import BaseModel, Field
from typing import Optional, List
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

class LeadStatusUpdate(BaseModel):
    status: str = Field(..., description="The status of the lead: new, contacted, follow_up, closed")
