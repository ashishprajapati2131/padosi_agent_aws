from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent
from fastapi_app.models.agent import Agent
from fastapi_app.repositories.agent_lead_repository import AgentLeadRepository
from fastapi_app.services.lock_unlock_service import LockUnlockService
from fastapi_app.schemas.leads import (
    LeadsListResponse, LeadStatusUpdate, LeadDetail, CaptureLeadRequest,
    LeadPreferencesRequest, LeadPreferencesResponse
)

router = APIRouter(
    prefix="/v1/agents/leads",
    tags=["Agent Leads"]
)

def get_lead_repository(db: Session = Depends(get_db)) -> AgentLeadRepository:
    return AgentLeadRepository(db)

@router.get("", response_model=LeadsListResponse)
def list_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str = Query(None, alias="status", description="Filter by lead status: new, contacted, follow_up, closed"),
    interaction_type: str = Query(None, description="Filter by interaction type: call, whatsapp, manual"),
    search: str = Query(None, description="Search term matching name, email, or mobile"),
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
    repo: AgentLeadRepository = Depends(get_lead_repository)
):
    """
    Get paginated, filtered list of leads for the authenticated agent.
    Includes lock/unlock metadata for UI gating.
    """
    lock_service = LockUnlockService(db)
    access_map = lock_service.get_feature_access_map(current_agent)
    lead_mgmt_access = access_map.get("lead_management", {})
    is_locked = lead_mgmt_access.get("is_locked", False)
    unlock_hint = lead_mgmt_access.get("unlock_hint")

    leads, total = repo.get_leads_paginated(
        agent_id=current_agent.id,
        page=page,
        page_size=page_size,
        status=status_filter,
        interaction_type=interaction_type,
        search=search
    )
    return LeadsListResponse(
        success=True,
        total=total,
        page=page,
        page_size=page_size,
        leads=leads,
        is_locked=is_locked,
        unlock_hint=unlock_hint
    )

@router.get("/preferences", response_model=LeadPreferencesResponse)
def get_lead_preferences(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
    repo: AgentLeadRepository = Depends(get_lead_repository)
):
    """
    Get lead receiving preferences for the authenticated agent.
    """
    pref = repo.get_preferences(current_agent.id)
    pref_data = {
        "leads_new_business": pref.leads_new_business if pref else True,
        "leads_portfolio_analysis": pref.leads_portfolio_analysis if pref else True,
        "portfolio_charging": pref.portfolio_charging if pref else "free",
        "portfolio_fee": float(pref.portfolio_fee) if pref and pref.portfolio_fee else 0.0,
        "leads_claims_support": pref.leads_claims_support if pref else True,
        "claims_charging": pref.claims_charging if pref else "free",
        "claims_fee_amount": float(pref.claims_fee_amount) if pref and pref.claims_fee_amount else 0.0,
        "claims_percent": float(pref.claims_percent) if pref and pref.claims_percent else 0.0
    }
    return LeadPreferencesResponse(
        success=True,
        data=pref_data
    )

@router.put("/preferences", response_model=LeadPreferencesResponse)
def update_lead_preferences(
    payload: LeadPreferencesRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
    repo: AgentLeadRepository = Depends(get_lead_repository)
):
    """
    Update lead receiving preferences (Guarded by lead_preferences lock).
    """
    lock_service = LockUnlockService(db)
    lock_service.require_feature_unlocked(current_agent, "lead_preferences")

    if payload.leads_portfolio_analysis:
        lock_service.require_feature_unlocked(current_agent, "lead_portfolio_analysis")
    if payload.leads_claims_support:
        lock_service.require_feature_unlocked(current_agent, "lead_claims_support")
    if payload.leads_new_business:
        lock_service.require_feature_unlocked(current_agent, "receive_leads")

    pref = repo.save_preferences(current_agent.id, payload.model_dump())
    return LeadPreferencesResponse(
        success=True,
        data={
            "leads_new_business": pref.leads_new_business,
            "leads_portfolio_analysis": pref.leads_portfolio_analysis,
            "portfolio_charging": pref.portfolio_charging,
            "portfolio_fee": float(pref.portfolio_fee or 0),
            "leads_claims_support": pref.leads_claims_support,
            "claims_charging": pref.claims_charging,
            "claims_fee_amount": float(pref.claims_fee_amount or 0),
            "claims_percent": float(pref.claims_percent or 0)
        },
        message="Lead preferences updated successfully."
    )

@router.post("/capture", response_model=LeadDetail)
def capture_lead(
    payload: CaptureLeadRequest,
    current_agent: Agent = Depends(get_current_agent),
    repo: AgentLeadRepository = Depends(get_lead_repository)
):
    """
    Agent manually records a customer enquiry / lead.
    """
    lead = repo.capture_lead(current_agent.id, payload.model_dump())
    return lead

@router.get("/{lead_id}", response_model=LeadDetail)
def get_lead_detail(
    lead_id: int,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
    repo: AgentLeadRepository = Depends(get_lead_repository)
):
    """
    Get full details of a specific lead belonging to the authenticated agent.
    Guarded by lead_management lock.
    """
    lock_service = LockUnlockService(db)
    lock_service.require_feature_unlocked(current_agent, "lead_management")

    lead = repo.get_by_id(current_agent.id, lead_id)
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found or does not belong to the authenticated agent."
        )
    return lead

@router.patch("/{lead_id}/status", response_model=LeadDetail)
def update_status(
    lead_id: int,
    payload: LeadStatusUpdate,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
    repo: AgentLeadRepository = Depends(get_lead_repository)
):
    """
    Update status of a specific lead belonging to the authenticated agent.
    Guarded by lead_management lock.
    """
    lock_service = LockUnlockService(db)
    lock_service.require_feature_unlocked(current_agent, "lead_management")

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
