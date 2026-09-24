from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional

from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_optional_agent
from fastapi_app.models.agent import Agent
from fastapi_app.schemas.plans import PlansListResponse
from fastapi_app.services.plan_service import PlanService

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
    List all active subscription plans (Starter, Professional, Exclusive).

    - Returns all live plans from the database.
    - Provides price breakdown: Actual Price vs Discounted Price + 18% GST (base, gst_amount, final).
    - Features / Unlocked benefits list per plan.
    - Highlights current logged-in agent plan (is_current_plan: true/false).
    - Shows applicable special upgrade discount (Trial discount / Referral discount / Agent reward).
    """
    service = PlanService(db)
    return service.get_plans_list(agent=current_agent)
