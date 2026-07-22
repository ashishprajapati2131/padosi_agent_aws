from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.repositories.agent_repository import AgentRepository
from app.services.public_profile_service import PublicProfileService
from app.schemas.public_profile import PublicProfileResponse
from app.dependencies.auth import get_current_agent
from app.models.agent import Agent

router = APIRouter(
    prefix="/api/v1/agents/public-profile",
    tags=["Agent Public Profile"]
)

@router.get("/{slug}", response_model=PublicProfileResponse)
def get_public_profile(
    slug: str,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Get the public profile of an agent by slug.
    Requires JWT Token Authentication.
    """
    agent_repo = AgentRepository(db)
    service = PublicProfileService(agent_repo)
    return service.get_public_profile(slug)
