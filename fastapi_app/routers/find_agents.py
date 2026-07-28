from fastapi import APIRouter, Query
from typing import List, Optional

from fastapi_app.schemas.agent_search import FindAgentsRequest, FindAgentsResponse
from fastapi_app.services.agent_search_service import AgentSearchService

router = APIRouter(
    prefix="/api/v1/find-agents",
    tags=["Find Agents"]
)

@router.get("", response_model=FindAgentsResponse, summary="Find Agents (GET)")
@router.get("/", response_model=FindAgentsResponse, include_in_schema=False)
def find_agents_get(
    pincode: Optional[str] = Query(None, description="6-digit Indian Pincode"),
    location: Optional[str] = Query(None, description="City, State, or Area search string"),
    lat: Optional[float] = Query(None, description="User Latitude"),
    lng: Optional[float] = Query(None, description="User Longitude"),
    ServiceType: Optional[List[str]] = Query(None, description="List of service types"),
    InsuranceType: Optional[List[str]] = Query(None, description="List of insurance types"),
    InsuranceCompany: Optional[List[str]] = Query(None, description="Selected insurance companies"),
    ClaimInsuranceCompany: Optional[str] = Query(None, description="Company name for claim support lookup"),
    ComplaintType: Optional[str] = Query(None, description="Complaint category for claim filter"),
    search: Optional[str] = Query(None, description="Keyword search for agent name, city, state"),
    sort_by: Optional[str] = Query("match", description="Sort option: distance | match | rating | experience"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(3, ge=1, le=3, description="Page size")
) -> FindAgentsResponse:
    """
    Hyperlocal Find Agent Search & Filtering API (GET).
    Accepts query parameters matching the web interface.
    """
    req = FindAgentsRequest(
        pincode=pincode,
        location=location,
        lat=lat,
        lng=lng,
        service_types=ServiceType or [],
        insurance_types=InsuranceType or [],
        insurance_companies=InsuranceCompany or [],
        claim_insurance_company=ClaimInsuranceCompany,
        complaint_type=ComplaintType,
        search=search,
        sort_by=sort_by or "match",
        page=page,
        page_size=page_size
    )
    return AgentSearchService.search_agents(req)
