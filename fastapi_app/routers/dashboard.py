from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies.auth import get_current_agent
from app.models.agent import Agent
from app.services.dashboard_service import DashboardService
from app.schemas.dashboard import DashboardResponse

router = APIRouter(
    prefix="/api/v1/agents",
    tags=["Dashboard"]
)

def get_dashboard_service(db: Session = Depends(get_db)) -> DashboardService:
    return DashboardService(db)

@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    current_agent: Agent = Depends(get_current_agent),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
):
    """
    Agent Dashboard
    Returns all dashboard data for the authenticated agent.
    Mirrors AgentDashboardController@index from the Laravel application.
    """
    return dashboard_service.get_dashboard(current_agent)
