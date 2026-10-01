from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional

from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent, get_optional_agent
from fastapi_app.models.agent import Agent
from fastapi_app.schemas.plans import (
    PlanFollowRequest,
    PlanScratchRequest,
    PlanUpgradeHandoffRequest,
    PlanUpgradeHandoffResponse,
    PlansListResponse,
)
from fastapi_app.services.plan_service import PlanService
from fastapi_app.services.plan_upgrade_handoff import issue_plan_upgrade_handoff

router = APIRouter(
    prefix="/v1/agents",
    tags=["Subscription Plans"]
)


@router.get("/plans", response_model=PlansListResponse)
@router.get("/plans/", response_model=PlansListResponse, include_in_schema=False)
def get_plans_list(
    current_agent: Optional[Agent] = Depends(get_optional_agent),
    db: Session = Depends(get_db)
):
    """
    List the app plans: Starter (Basic) and Professional.

    Prices come from the admin choose-plan settings. The card shows the list
    price (1999 / 9999) until this agent scratches. Scratch and follow are
    recorded with POST /plans/scratch and POST /plans/follow.
    """
    service = PlanService(db)
    return service.get_plans_list(agent=current_agent)


@router.post("/plans/scratch", response_model=PlansListResponse)
def scratch_plan(
    payload: PlanScratchRequest,
    agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """Reveal the admin scratch price for one plan. Idempotent."""
    return PlanService(db).record_scratch(agent, payload.plan_slug)


@router.post("/plans/follow", response_model=PlansListResponse)
def follow_platform(
    payload: PlanFollowRequest,
    agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """Record one social follow. The admin follow tier applies after scratch."""
    return PlanService(db).record_follow(agent, payload.platform)


@router.post("/plan-upgrade/handoff", response_model=PlanUpgradeHandoffResponse)
def create_plan_upgrade_handoff(
    body: PlanUpgradeHandoffRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
):
    """
    One-time website URL for the logged-in agent.

    The Android app opens `url` in a Chrome Custom Tab. The website logs that
    agent in and opens the upgrade payment for `plan_slug`. The link expires
    in 3 minutes and works once. The agent is taken from the bearer token.
    """
    return issue_plan_upgrade_handoff(db, current_agent, body.plan_slug)
