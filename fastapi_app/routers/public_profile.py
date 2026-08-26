from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from fastapi_app.database import get_db
from fastapi_app.repositories.agent_repository import AgentRepository
from fastapi_app.services.public_profile_service import PublicProfileService
from fastapi_app.schemas.public_profile import PublicProfileResponse

router = APIRouter(
    prefix="/api/v1/agents/public-profile",
    tags=["Agent Public Profile"]
)

@router.get("/{slug}", response_model=PublicProfileResponse)
def get_public_profile(
    slug: str,
    db: Session = Depends(get_db)
):
    """
    Get the public profile of an agent by slug.

    Unauthenticated, mirroring Django's `/profile/<slug>/`, so shared links
    open for prospective customers. Agent-controlled visibility flags are
    enforced in the service layer.
    """
    agent_repo = AgentRepository(db)
    service = PublicProfileService(agent_repo)
    return service.get_public_profile(slug)
