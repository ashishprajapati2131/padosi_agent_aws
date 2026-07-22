from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies.auth import get_current_agent
from app.models.agent import Agent
from app.repositories.agent_lead_repository import AgentLeadRepository
from app.schemas.leads import LeadsListResponse, LeadStatusUpdate, LeadDetail

router = APIRouter(
    prefix="/api/v1/agents/leads",
    tags=["Agent Leads"]
)

def get_lead_repository(db: Session = Depends(get_db)) -> AgentLeadRepository:
    return AgentLeadRepository(db)

@router.get("", response_model=LeadsListResponse)
def list_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query(None, description="Filter by lead status: new, contacted, follow_up, closed"),
    interaction_type: str = Query(None, description="Filter by interaction type: call, whatsapp"),
    search: str = Query(None, description="Search term matching name, email, or mobile"),
    current_agent: Agent = Depends(get_current_agent),
    repo: AgentLeadRepository = Depends(get_lead_repository)
):
    """
    Get paginated, filtered list of leads for the authenticated agent.
    """
    leads, total = repo.get_leads_paginated(
        agent_id=current_agent.id,
        page=page,
        page_size=page_size,
        status=status,
        interaction_type=interaction_type,
        search=search
    )
    return LeadsListResponse(
        success=True,
        total=total,
        page=page,
        page_size=page_size,
        leads=leads
    )

@router.patch("/{lead_id}/status", response_model=LeadDetail)
def update_status(
    lead_id: int,
    payload: LeadStatusUpdate,
    current_agent: Agent = Depends(get_current_agent),
    repo: AgentLeadRepository = Depends(get_lead_repository)
):
    """
    Update status of a specific lead belonging to the authenticated agent.
    """
    allowed_statuses = ["new", "contacted", "follow_up", "closed"]
    if payload.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status. Allowed values are: {', '.join(allowed_statuses)}"
        )
    
    lead = repo.update_lead_status(
        agent_id=current_agent.id,
        lead_id=lead_id,
        status=payload.status
    )
    
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found or does not belong to the authenticated agent."
        )
        
    return lead
